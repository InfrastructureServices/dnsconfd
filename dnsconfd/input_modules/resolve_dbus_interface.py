import logging
import dbus.service
from dbus.service import BusName

from dnsconfd import ResolvingMode
from dnsconfd.network_objects import InterfaceConfiguration
from dnsconfd.network_objects import ServerDescription
from dnsconfd.fsm import DnsconfdContext
from dnsconfd.fsm import ContextEvent
from dnsconfd.network_objects import DnsProtocol


class ResolveDbusInterface(dbus.service.Object):
    def __init__(self, runtime_context: DnsconfdContext, config):
        """ Implementation of the Resolve1 DBUS interface

        :param runtime_context: execution context of Dnsconfd
        :param config: configuration dictionary
        """
        super().__init__(object_path="/org/freedesktop/resolve1",
                         bus_name=BusName(config["dbus_name"],
                                          dbus.SystemBus()))
        self.interfaces: dict[int, InterfaceConfiguration] = {}
        self.runtime_context = runtime_context
        self.prio_wire = config["prioritize_wire"]
        self.dnssec_enabled = config["dnssec_enabled"]
        self.ignore_api = config["ignore_api"]
        self.lgr = logging.getLogger(self.__class__.__name__)

    # Implements systemd-resolved interfaces defined at:
    # freedesktop.org/software/systemd/man/latest/org.freedesktop.resolve1.html
    # or man 5 org.freedesktop.resolve1

    @dbus.service.method(dbus_interface='org.freedesktop.resolve1.Manager',
                         in_signature='ia(iay)', out_signature='')
    def SetLinkDNS(self,
                   interface_index: int,
                   addresses: list[(int, bytearray)]):
        self.lgr.debug("SetLinkDNS called, interface index: "
                       "%s, addresses: %s", interface_index, addresses)
        if self.ignore_api:
            self.lgr.debug("Call ignored, since ignore_api is set")
        interface_cfg = self._iface_config(interface_index)
        prio = self._ifprio(interface_cfg) if self.prio_wire else 100
        servers = [ServerDescription(fam, addr, priority=prio)
                   for fam, addr in addresses]
        interface_cfg.servers = servers
        servers_to_string = ' '.join([str(server) for server in servers])
        self.lgr.info("Incoming DNS servers on %s:%s",
                      interface_cfg.get_if_name(interface_cfg.index),
                      servers_to_string)
        self._update_if_ready(interface_cfg)

    @dbus.service.method(dbus_interface='org.freedesktop.resolve1.Manager',
                         in_signature='ia(iayqs)', out_signature='')
    def SetLinkDNSEx(self,
                     interface_index: int,
                     addresses: list[(int, bytearray, int, str)]):
        self.lgr.debug("SetLinkDNSEx called, interface index: "
                       "%s, addresses: %s", interface_index, addresses)
        if self.ignore_api:
            self.lgr.debug("Call ignored, since ignore_api is set")
        interface_cfg = self._iface_config(interface_index)
        prio = self._ifprio(interface_cfg) if self.prio_wire else 100
        servers = [ServerDescription(fam, addr, port, name, prio)
                   for fam, addr, port, name in addresses]
        interface_cfg.servers = servers
        servers_to_string = ' '.join([str(server) for server in servers])
        self.lgr.info("Incoming DNS servers on %s:%s",
                      interface_cfg.get_if_name(interface_cfg.index),
                      servers_to_string)
        self._update_if_ready(interface_cfg)

    @dbus.service.method(dbus_interface='org.freedesktop.resolve1.Manager',
                         in_signature='ia(sb)', out_signature='')
    def SetLinkDomains(self, interface_index: int, domains: list[(str, bool)]):
        self.lgr.debug("SetLinkDomains called, interface index: "
                       "%s, domains: %s", interface_index, domains)
        if self.ignore_api:
            self.lgr.debug("Call ignored, since ignore_api is set")
        interface_cfg = self._iface_config(interface_index)
        # not is_routing because we consider this boolean in a sense
        # 'should be added to search domains?'
        interface_cfg.domains = [(str(domain), not bool(is_routing))
                                 for domain, is_routing in domains]
        self._update_if_ready(interface_cfg)

    @dbus.service.method(dbus_interface='org.freedesktop.resolve1.Manager',
                         in_signature='ib', out_signature='')
    def SetLinkDefaultRoute(self, interface_index: int, is_default: bool):
        self.lgr.debug("SetLinkDefaultRoute called, interface index: "
                       "%s, is_default: %s", interface_index, is_default)
        if self.ignore_api:
            self.lgr.debug("Call ignored, since ignore_api is set")
        interface_cfg = self._iface_config(interface_index)
        interface_cfg.is_default = is_default
        self._update_if_ready(interface_cfg)

    @dbus.service.method(dbus_interface='org.freedesktop.resolve1.Manager',
                         in_signature='is', out_signature='')
    def SetLinkLLMNR(self, interface_index: int, mode: str):
        # unbound does not support LLMNR
        self.lgr.debug("SetLinkLLMNR called, and ignored")

    @dbus.service.method(dbus_interface='org.freedesktop.resolve1.Manager',
                         in_signature='is', out_signature='')
    def SetLinkMulticastDNS(self, interface_index: int, mode: str):
        self.lgr.debug("SetLinkMulticastDNS called, and ignored")

    @dbus.service.method(dbus_interface='org.freedesktop.resolve1.Manager',
                         in_signature='is', out_signature='')
    def SetLinkDNSOverTLS(self, interface_index: int, mode: str):
        self.lgr.debug("SetLinkDNSOverTLS called, interface index: "
                       "%s, mode: '%s'", interface_index, mode)
        if self.ignore_api:
            self.lgr.debug("Call ignored, since ignore_api is set")
        interface_cfg = self.interfaces[interface_index]
        if mode in ["yes", "opportunistic"]:
            interface_cfg.dns_over_tls = True
        else:
            interface_cfg.dns_over_tls = False
        self._update_if_ready(interface_cfg)

    @dbus.service.method(dbus_interface='org.freedesktop.resolve1.Manager',
                         in_signature='is', out_signature='')
    def SetLinkDNSSEC(self, interface_index: int, mode: str):
        self.lgr.debug("SetLinkDNSSEC called, "
                       "interface index: %s, mode: %s",
                       interface_index, mode)
        if self.ignore_api:
            self.lgr.debug("Call ignored, since ignore_api is set")
        interface_cfg = self._iface_config(interface_index)
        if mode in ["no", "allow-downgrade"]:
            interface_cfg.dnssec = False
        else:
            interface_cfg.dnssec = True
        self._update_if_ready(interface_cfg)

    @dbus.service.method(dbus_interface='org.freedesktop.resolve1.Manager',
                         in_signature='ias', out_signature='')
    def SetLinkDNSSECNegativeTrustAnchors(self,
                                          interface_index: int,
                                          names: list[str]):
        self.lgr.debug("SetLinkDNSSECNegativeTrustAnchors called and ignored, "
                       "interface index: %s, names: %s",
                       interface_index, names)

    @dbus.service.method(dbus_interface='org.freedesktop.resolve1.Manager',
                         in_signature='i', out_signature='')
    def RevertLink(self, interface_index: int):
        self.lgr.debug("RevertLink called and ignored, "
                       "interface index: %s", interface_index)

    @dbus.service.method(dbus_interface='org.freedesktop.resolve1.Manager',
                         in_signature='', out_signature='')
    def FlushCaches(self):
        # TODO: we need ability to flush just a subtree, not always all records
        self.lgr.debug("FlushCaches called and ignored")

    @dbus.service.method(dbus_interface='org.freedesktop.resolve1.Dnsconfd',
                         in_signature='b', out_signature='s')
    def Status(self, json_format: bool):
        return self.runtime_context.get_status(json_format)

    @dbus.service.method(dbus_interface='org.freedesktop.resolve1.Dnsconfd',
                         in_signature='', out_signature='bs')
    def Reload(self):
        self.lgr.info("Received request for reload of plugin")
        return self.runtime_context.reload_service()

    def _iface_config(self, interface_id: int):
        """Get existing or create new default interface network_objects."""
        return self.interfaces.setdefault(interface_id,
                                          InterfaceConfiguration(interface_id))

    def _ifprio(self, interface_cfg: InterfaceConfiguration) -> int:
        if interface_cfg.is_interface_wireless(interface_cfg.index):
            self.lgr.debug("Interface %s is wireless",
                           interface_cfg.index)
            return 50
        return 100

    def _update_if_ready(self, interface: InterfaceConfiguration):
        ips_to_interface = {}
        if interface.is_ready():
            self.lgr.info("API pushing update %s", interface)
            servers: list[ServerDescription] = []
            for cur_interface in self.interfaces.values():
                if not cur_interface.servers:
                    continue
                if_index = int(cur_interface)
                if_name = InterfaceConfiguration.get_if_name(if_index,
                                                             strict=True)
                if if_name is None:
                    self.lgr.error("Interface with index %s does not have "
                                   "a name, its servers will not be used",
                                   if_index)
                    continue
                for server in cur_interface.servers:
                    routing_domains = []
                    search_domains = []
                    for domain, search in cur_interface.domains:
                        if search:
                            search_domains.append(domain)
                        routing_domains.append(domain)
                    if cur_interface.is_default:
                        routing_domains.append(".")
                    if cur_interface.dns_over_tls:
                        protocol = DnsProtocol.DNS_PLUS_TLS
                    else:
                        protocol = DnsProtocol.DNS_PLUS_UDP
                    if server.address in ips_to_interface:
                        if ips_to_interface[server.address] != if_index:
                            self.lgr.warning("2 servers with the same "
                                             "ip can not be bound to 2 "
                                             "interfaces, ignoring the "
                                             "one for interface %s",
                                             if_index)
                            continue
                    else:
                        ips_to_interface[server.address] = if_index

                    # since NetworkManager does not support dnssec config
                    # value, in this API we will set dnssec according
                    # to value from configuration

                    new_srv = ServerDescription(server.address_family,
                                                server.address,
                                                server.port,
                                                server.name,
                                                server.priority,
                                                routing_domains,
                                                search_domains,
                                                if_name,
                                                protocol,
                                                self.dnssec_enabled)

                    servers.append(new_srv)

            event = ContextEvent("UPDATE", (servers, ResolvingMode.BACKUP))
            self.lgr.debug("UPDATE IS %s, %s", interface.index,
                           [a.to_dict() for a in servers])
            self.runtime_context.transition_function(event)
