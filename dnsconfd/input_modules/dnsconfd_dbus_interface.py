from dnsconfd.network_objects import ServerDescription, InterfaceConfiguration
from dnsconfd.network_objects import DnsProtocol
from dnsconfd.fsm import DnsconfdContext
from dnsconfd.fsm import ContextEvent

import ipaddress
from socket import AF_INET, AF_INET6
import typing
import logging
import dbus.service
from dbus.service import BusName
import re


class DnsconfdDbusInterface(dbus.service.Object):
    def __init__(self, runtime_context: DnsconfdContext, config):
        super().__init__(object_path="/com/redhat/dnsconfd",
                         bus_name=BusName(config["dbus_name"],
                                          dbus.SystemBus()))
        self.runtime_context = runtime_context
        self.prio_wire = config["prioritize_wire"]
        self.ignore_api = config["ignore_api"]
        self.lgr = logging.getLogger(self.__class__.__name__)
        domain_re = r"((?!-)([A-Za-z0-9-]){1,63}(?<!-)\.?)+|\."
        sni_re = r"((?!-)([A-Za-z0-9-]){1,63}(?<!-)\.?)+"
        self.domain_pattern = re.compile(domain_re)
        self.sni_pattern = re.compile(sni_re)

    @dbus.service.method(dbus_interface='com.redhat.dnsconfd.Manager',
                         in_signature='aa{sv}', out_signature='bs')
    def Update(self, servers: list[dict[str, typing.Any]]):
        new_servers = []
        self.lgr.info(f"update dbus method called with args: {servers}")
        if self.ignore_api:
            return True, "Configured to ignore"

        for index, server in enumerate(servers):
            self.lgr.debug(f"processing server: {server}")
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
                else:
                    port = int(server["port"])

            protocol = DnsProtocol.PLAIN
            if server.get("protocol", None) is not None:
                if (not isinstance(server["protocol"], str)
                        or server["protocol"] not in ["plain", "DoT"]):
                    msg = f"{index + 1}. server has unknown protocol " \
                          f"{server["protocol"]}, only plain or DoT allowed"
                    self.lgr.error(msg)
                    return False, msg
                elif server["protocol"] == "DoT":
                    protocol = DnsProtocol.DNS_OVER_TLS

            sni = None
            if server.get("sni", None) is not None:
                if (not isinstance(server["sni"], str)
                        or not self.sni_pattern.fullmatch(server["sni"])):
                    msg = f"{index + 1}. server sni is not "\
                          f"allowed {server["sni"]}"
                    self.lgr.error(msg)
                    return False, msg
                else:
                    sni = str(server["sni"])

            domains = None
            if server.get("domains", None) is not None:
                if not isinstance(server["domains"], list):
                    msg = f"{index + 1}. server domains is not "\
                          f"list {server["domains"]}"
                    self.lgr.error(msg)
                    return False, msg
                elif [x for x in server["domains"]
                      if not isinstance(x, tuple)]:
                    msg = f"{index + 1}. server domains must all be tuples "\
                          f"{server["domains"]}"
                    self.lgr.error(msg)
                    return False, msg
                elif [x for x in server["domains"] if len(x) != 2]:
                    msg = f"{index + 1}. server domains must all be tuples "\
                          f"with 2 members {server["domains"]}"
                    self.lgr.error(msg)
                    return False, msg

                for domain, search in server["domains"]:
                    if not isinstance(search, bool):
                        msg = f"{index + 1}. server domains second member " \
                              f"has to be bool {server["domains"]}"
                        self.lgr.error(msg)
                        return False, msg
                    elif not self.domain_pattern.fullmatch(domain):
                        msg = (f"{index + 1}."
                               f"server domain is not domain {domain}")
                        self.lgr.error(msg)
                        return False, msg
                domains = [(str(domain), bool(search))
                           for (domain, search) in server["domains"]]

            interface = None
            is_wireless = False
            if server.get("interface", None) is not None:
                if not isinstance(server["interface"], int):
                    msg = (f"{index + 1}. server has bad interface "
                           f"{server["interface"]}")
                    self.lgr.error(msg)
                    return False, msg
                else:
                    interface = int(server["interface"])
                    is_wireless = (self.prio_wire
                                   and (InterfaceConfiguration.
                                        is_interface_wireless(interface)))
            dnssec = False

            if server.get("dnssec", None) is not None:
                if not isinstance(server["dnssec"], bool):
                    msg = f"{index + 1}. dnssec is not bool"
                    self.lgr.error(msg)
                    return False, msg
                else:
                    dnssec = bool(server["dnssec"])

            # you may notice the type conversions throughout this method,
            # these are present to get rid of dbus types and prevent
            # unexpected problems in further processing

            addr_family = AF_INET if parsed_address.version == 4 else AF_INET6
            serv_desc = ServerDescription(addr_family,
                                          parsed_address.packed,
                                          port,
                                          sni,
                                          priority=50 if is_wireless else 100,
                                          domains=domains,
                                          interface=interface,
                                          protocol=protocol,
                                          dnssec=dnssec)
            new_servers.append(serv_desc)
        event = ContextEvent("UPDATE", new_servers)
        self.runtime_context.transition_function(event)
        return True, "Done"

    @dbus.service.method(dbus_interface='com.redhat.dnsconfd.Manager',
                         in_signature='b', out_signature='s')
    def Status(self, json_format: bool):
        return self.runtime_context.get_status(json_format)

    @dbus.service.method(dbus_interface='com.redhat.dnsconfd.Manager',
                         in_signature='', out_signature='s')
    def Reload(self):
        self.lgr.info("Received request for reload of plugin")
        return self.runtime_context.reload_service()
