import ipaddress
from socket import AF_INET, AF_INET6
import typing
import logging
import re
import dbus.service
from dbus.service import BusName

from dnsconfd.network_objects import ServerDescription, InterfaceConfiguration
from dnsconfd.network_objects import DnsProtocol
from dnsconfd.input_modules import ResolvingMode
from dnsconfd.fsm import DnsconfdContext, ContextEvent


class DnsconfdDbusInterface(dbus.service.Object):
    def __init__(self, runtime_context: DnsconfdContext, config: dict):
        """ Implementation of the Dnsconfd DBUS interface

        :param runtime_context: execution context of Dnsconfd
        :param config: configuration dictionary
        """
        super().__init__(object_path="/com/redhat/dnsconfd",
                         bus_name=BusName(config["dbus_name"],
                                          dbus.SystemBus()))
        self.runtime_context = runtime_context
        self.prio_wire = config["prioritize_wire"]
        self.ignore_api = config["ignore_api"]
        self.dnssec_enabled = config["dnssec_enabled"]
        self.lgr = logging.getLogger(self.__class__.__name__)
        domain_re = r"((?!-)([A-Za-z0-9-]){1,63}(?<!-)\.?)+|\."
        search_re = r"((?!-)([A-Za-z0-9-]){1,63}(?<!-)\.?)+"
        name_re = r"((?!-)([A-Za-z0-9-]){1,63}(?<!-)\.?)+"
        self.domain_pattern = re.compile(domain_re)
        self.search_pattern = re.compile(search_re)
        self.name_pattern = re.compile(name_re)

    @dbus.service.method(dbus_interface='com.redhat.dnsconfd.Manager',
                         in_signature='aa{sv}u', out_signature='bs')
    def Update(self, servers: list[dict[str, typing.Any]], mode: int) \
            -> tuple[bool, str]:
        """ Update forwarders that should be used

        :param servers: list of dictionaries describing servers.
        Members are described in DBUS API documentation
        :param mode: Resolving mode representing how the servers should be
                     handled
        :return: Tuple with True or False and message with more info
        """
        new_servers = []
        self.lgr.info("Update dbus method called with args: %s", servers)
        if self.ignore_api:
            return True, "Configured to ignore"
        ips_to_interface = {}

        if mode not in [0, 1, 2]:
            msg = f"Mode {mode} not in allowed range 0-2"
            self.lgr.error(msg)
            return False, msg

        for index, server in enumerate(servers):
            self.lgr.debug("processing server: %s", server)
            if server.get("address", None) is None:
                msg = f"{index + 1}. server in update has no address"
                self.lgr.error(msg)
                return False, msg
            try:
                parsed_address = ipaddress.ip_address(server["address"])
            except ValueError:
                msg = f"{index + 1}. server has incorrect " \
                      f"ip address {server["address"]}"
                self.lgr.error(msg)
                return False, msg

            port = None
            if server.get("port", None) is not None:
                if (not isinstance(server["port"], int)
                        or not 0 < server["port"] < 65536):
                    msg = f"{index + 1}. server has bad port {server["port"]}"
                    self.lgr.error(msg)
                    return False, msg
                port = int(server["port"])

            protocol = DnsProtocol.PLAIN
            if server.get("protocol", None) is not None:
                if (not isinstance(server["protocol"], str)
                        or server["protocol"].lower() not in ["plain", "dot"]):
                    msg = f"{index + 1}. server has unknown protocol " \
                          f"{server["protocol"]}, only plain or DoT allowed"
                    self.lgr.error(msg)
                    return False, msg
                if server["protocol"].lower() == "dot":
                    protocol = DnsProtocol.DNS_OVER_TLS

            name = None
            if server.get("name", None) is not None:
                if (not isinstance(server["name"], str)
                        or not self.name_pattern.fullmatch(server["name"])):
                    msg = f"{index + 1}. server name is not " \
                          f"allowed {server["name"]}"
                    self.lgr.error(msg)
                    return False, msg
                name = str(server["name"])

            routing_domains = None
            if server.get("routing_domains", None) is not None:
                if not isinstance(server["routing_domains"], list):
                    msg = f"{index + 1}. server routing domains is not " \
                          f"list {server["domains"]}"
                    self.lgr.error(msg)
                    return False, msg
                for domain in server["routing_domains"]:
                    if not isinstance(domain, str):
                        msg = (f"{index + 1}."
                               f"server routing domain is not string")
                        self.lgr.error(msg)
                        return False, msg
                    if not self.domain_pattern.fullmatch(domain):
                        msg = (f"{index + 1}."
                               f"server routing domain is not domain {domain}")
                        self.lgr.error(msg)
                        return False, msg
                routing_domains = server["routing_domains"]

            search_domains = None
            if server.get("search_domains", None) is not None:
                if not isinstance(server["search_domains"], list):
                    msg = f"{index + 1}. server search domains is not " \
                          f"list {server["domains"]}"
                    self.lgr.error(msg)
                    return False, msg
                for domain in server["search_domains"]:
                    if not isinstance(domain, str):
                        msg = (f"{index + 1}."
                               f"server search domain is not string")
                        self.lgr.error(msg)
                        return False, msg
                    if not self.search_pattern.fullmatch(domain):
                        msg = (f"{index + 1}."
                               f"server search domain is not domain {domain}")
                        self.lgr.error(msg)
                        return False, msg
                search_domains = server["search_domains"]

            interface = None
            is_wireless = False
            if server.get("interface", None) is not None:
                if not isinstance(server["interface"], int):
                    msg = (f"{index + 1}. server has bad interface "
                           f"{server["interface"]}")
                    self.lgr.error(msg)
                    return False, msg
                interface = int(server["interface"])
                is_wireless = (self.prio_wire
                               and (InterfaceConfiguration.
                                    is_interface_wireless(interface)))

            if interface:
                parsed_addr_str = str(parsed_address)
                if (parsed_addr_str in ips_to_interface
                        and ips_to_interface[parsed_addr_str] != interface):
                    self.lgr.warning("2 servers with the same IP can not "
                                     "be bound to 2 different interfaces, "
                                     "ignoring server with interface %s",
                                     interface)
                    continue
                else:
                    ips_to_interface[parsed_addr_str] = interface

            dnssec = False
            if server.get("dnssec", None) is not None:
                if not isinstance(server["dnssec"], bool):
                    msg = f"{index + 1}. dnssec is not bool"
                    self.lgr.error(msg)
                    return False, msg
                dnssec = bool(server["dnssec"])

            if (self.dnssec_enabled and not dnssec
                    and (not routing_domains
                         or [x for x in routing_domains if x == '.'])):
                msg = ("Server used for . domain can not have disabled "
                       "dnssec when it is enabled by configuration")
                self.lgr.error(msg)
                return False, msg

            networks = None
            if server.get("networks", None) is not None:
                if not isinstance(server["networks"], list):
                    msg = f"{index + 1}. server networks is not " \
                          f"list {server["networks"]}"
                    self.lgr.error(msg)
                    return False, msg
                networks = []
                for net in server["networks"]:
                    try:
                        networks.append(ipaddress.ip_network(net))
                    except ValueError:
                        msg = f"{index + 1}. server network is not " \
                              f"valid network {net}"
                        self.lgr.error(msg)
                        return False, msg

            firewall_zone = None
            if server.get("firewall_zone", None) is not None:
                if not isinstance(server["firewall_zone"], str):
                    msg = (f"{index + 1}."
                           f"server search domain is not string")
                    self.lgr.error(msg)
                    return False, msg
                firewall_zone = server["firewall_zone"]

            # you may notice the type conversions throughout this method,
            # these are present to get rid of dbus types and prevent
            # unexpected problems in further processing

            addr_family = AF_INET if parsed_address.version == 4 else AF_INET6
            serv_desc = ServerDescription(addr_family,
                                          parsed_address.packed,
                                          port,
                                          name,
                                          priority=50 if is_wireless else 100,
                                          routing_domains=routing_domains,
                                          search_domains=search_domains,
                                          interface=interface,
                                          protocol=protocol,
                                          dnssec=dnssec,
                                          networks=networks,
                                          firewall_zone=firewall_zone)
            new_servers.append(serv_desc)
        event = ContextEvent("UPDATE",
                             (new_servers, ResolvingMode(mode)))
        self.runtime_context.transition_function(event)
        return True, "Done"

    @dbus.service.method(dbus_interface='com.redhat.dnsconfd.Manager',
                         in_signature='b', out_signature='s')
    def Status(self, json_format: bool):
        """ Get status of Dnsconfd

        :param json_format: True if output should be JSON
        :return: string with status
        """
        return self.runtime_context.get_status(json_format)

    @dbus.service.method(dbus_interface='com.redhat.dnsconfd.Manager',
                         in_signature='', out_signature='bs')
    def Reload(self) -> tuple[bool, str]:
        """ Reload configuration of underlying cache service

        :return: Tuple with True or False and message with more info
        """
        self.lgr.info("Received request for reload of plugin")
        return self.runtime_context.reload_service()
