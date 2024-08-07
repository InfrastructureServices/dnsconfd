from dnsconfd.network_objects import InterfaceConfiguration
from dnsconfd.network_objects import ServerDescription
from dnsconfd.fsm import DnsconfdContext
from dnsconfd.fsm import ContextEvent

import logging
import dbus.service
from dbus.service import BusName


class ResolveDbusInterface(dbus.service.Object):
    def __init__(self, runtime_context: DnsconfdContext, config):
        super().__init__(object_path="/org/freedesktop/resolve1",
                         bus_name=BusName(config["dbus_name"],
                                          dbus.SystemBus()))
        self.interfaces: dict[int, InterfaceConfiguration] = {}
        self.runtime_context = runtime_context
        self.prio_wire = config["prioritize_wire"] is True
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
                       f"{interface_index}, addresses: {addresses}")
        interface_cfg = self._iface_config(interface_index)
        prio = self._ifprio(interface_cfg) if self.prio_wire else 100
        servers = [ServerDescription(fam, addr, priority=prio)
                   for fam, addr in addresses]
        interface_cfg.servers = servers
        servers_to_string = ' '.join([str(server) for server in servers])
        self.lgr.info("Incoming DNS servers on "
                      f"{interface_cfg.get_if_name()}: {servers_to_string}")
        self._update_if_ready(interface_cfg)

    @dbus.service.method(dbus_interface='org.freedesktop.resolve1.Manager',
                         in_signature='ia(iayqs)', out_signature='')
    def SetLinkDNSEx(self,
                     interface_index: int,
                     addresses: list[(int, bytearray, int, str)]):
        self.lgr.debug("SetLinkDNSEx called, interface index: "
                       f"{interface_index}, addresses: {addresses}")
        interface_cfg = self._iface_config(interface_index)
        prio = self._ifprio(interface_cfg) if self.prio_wire else 100
        servers = [ServerDescription(fam, addr, port, sni, prio)
                   for fam, addr, port, sni in addresses]
        interface_cfg.servers = servers
        servers_to_string = ' '.join([str(server) for server in servers])
        self.lgr.info("Incoming DNS servers on "
                      f"{interface_cfg.get_if_name()}: {servers_to_string}")
        self._update_if_ready(interface_cfg)

    @dbus.service.method(dbus_interface='org.freedesktop.resolve1.Manager',
                         in_signature='ia(sb)', out_signature='')
    def SetLinkDomains(self, interface_index: int, domains: list[(str, bool)]):
        self.lgr.debug("SetLinkDomains called, interface index: "
                       f"{interface_index}, domains: {domains}")
        interface_cfg = self._iface_config(interface_index)
        interface_cfg.domains = [(str(domain), bool(is_routing))
                                 for domain, is_routing in domains]
        self._update_if_ready(interface_cfg)

    @dbus.service.method(dbus_interface='org.freedesktop.resolve1.Manager',
                         in_signature='ib', out_signature='')
    def SetLinkDefaultRoute(self, interface_index: int, is_default: bool):
        self.lgr.debug("SetLinkDefaultRoute called, interface index: "
                       f"{interface_index}, is_default: {is_default}")
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
                       f"{interface_index}, mode: '{mode}'")
        interface_cfg = self.interfaces[interface_index]
        if mode == "yes" or mode == "opportunistic":
            interface_cfg.dns_over_tls = True
            for server in interface_cfg.servers:
                server.tls = True
        else:
            interface_cfg.dns_over_tls = False
            for server in interface_cfg.servers:
                server.tls = False
        self._update_if_ready(interface_cfg)

    @dbus.service.method(dbus_interface='org.freedesktop.resolve1.Manager',
                         in_signature='is', out_signature='')
    def SetLinkDNSSEC(self, interface_index: int, mode: str):
        self.lgr.debug("SetLinkDNSSEC called and ignored, "
                       f"interface index: {interface_index}, mode: {mode}")
        interface_cfg = self._iface_config(interface_index)
        if mode == "no" or mode == "allow-downgrade":
            interface_cfg.dns_over_tls = False
        else:
            interface_cfg.dns_over_tls = True
        self._update_if_ready(interface_cfg)

    @dbus.service.method(dbus_interface='org.freedesktop.resolve1.Manager',
                         in_signature='ias', out_signature='')
    def SetLinkDNSSECNegativeTrustAnchors(self,
                                          interface_index: int,
                                          names: list[str]):
        self.lgr.debug("SetLinkDNSSECNegativeTrustAnchors called and ignored, "
                       f"interface index: {interface_index}, names: {names}")

    @dbus.service.method(dbus_interface='org.freedesktop.resolve1.Manager',
                         in_signature='i', out_signature='')
    def RevertLink(self, interface_index: int):
        self.lgr.debug("RevertLink called and ignored, "
                       f"interface index: {interface_index}")

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
                         in_signature='', out_signature='s')
    def Reload(self):
        self.lgr.info("Received request for reload of plugin")
        return self.runtime_context.reload_service()

    def _iface_config(self, interface_id: int):
        """Get existing or create new default interface network_objects."""
        return self.interfaces.setdefault(interface_id,
                                          InterfaceConfiguration(interface_id))

    def _ifprio(self, interface_cfg: InterfaceConfiguration) -> int:
        if interface_cfg.is_interface_wireless():
            self.lgr.debug("Interface "
                           f"{interface_cfg.interface_index} is wireless")
            return 50
        return 100

    def _update_if_ready(self, interface: InterfaceConfiguration):
        if interface.is_ready():
            event = ContextEvent("UPDATE", interface)
            self.runtime_context.transition_function(event)
