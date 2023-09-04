from dnsconfd import SystemManager
from dnsconfd.configuration import InterfaceConfiguration
from dnsconfd.configuration import ServerDescription
from dnsconfd.dns_managers import UnboundManager

import signal
import logging as lgr
import sys

import dbus
import dbus.service


class DnsconfdContext(dbus.service.Object):
    def __init__(self, object_path, bus_name):
        super().__init__(object_path=object_path, bus_name=bus_name)
        self.dns_mgr = None
        self.sys_mgr = SystemManager()
        self.interfaces: dict[InterfaceConfiguration] = {}

    def signal_handler(self, signum):
        lgr.info(f"Caught signal {signal.strsignal(signum)}, shutting down")
        if self.sys_mgr.resolvconf_altered:
            self.sys_mgr.revertResolvconf()
        if self.dns_mgr is not None:
            self.dns_mgr.stop()
            self.dns_mgr.clean()
        sys.exit(0)

    def start_service(self):
        self.dns_mgr = UnboundManager()
        self.dns_mgr.configure()
        self.dns_mgr.start()
        self.sys_mgr.setResolvconf()

    # From network manager code investigation it seems that these methods are called in
    # the following sequence: SetLinkDomains, SetLinkDefaultRoute, SetLinkMulticastDNS,
    # SetLinkLLMNR, SetLinkDNS, SetLinkDNSOverTLS
    # until proven otherwise, we will expect this to be true at all cases

    @dbus.service.method(dbus_interface='org.freedesktop.resolve1.Manager',
                         in_signature='ia(iay)', out_signature='')
    def SetLinkDNS(self, interface_index: int, addresses: list[(int, bytearray)]):
        lgr.info(f"SetLinkDNS called, interface index: {interface_index}, addresses: {addresses}")
        interface_cfg = self.interfaces.get(interface_index, InterfaceConfiguration(interface_index))
        prio = 50 if interface_cfg.isInterfaceWireless() else 100
        servers = [ServerDescription(addr, address_family=fam, priority=prio) for fam, addr in addresses]
        interface_cfg.servers = servers
        self.interfaces[interface_index] = interface_cfg

    @dbus.service.method(dbus_interface='org.freedesktop.resolve1.Manager',
                         in_signature='ia(iayqs)', out_signature='')
    def SetLinkDNSEx(self, interface_index: int, addresses: list[(int, bytearray, int, str)]):
        lgr.info(f"SetLinkDNSEx called, interface index: {interface_index}, addresses: {addresses}")
        prio = 50 if interface_cfg.isInterfaceWireless() else 100
        interface_cfg = self.interfaces.get(interface_index, InterfaceConfiguration(interface_index))
        servers = [ServerDescription(addr, port, sni, fam, prio) for fam, addr, port, sni in addresses]
        interface_cfg.servers = servers
        self.interfaces[interface_index] = interface_cfg

    @dbus.service.method(dbus_interface='org.freedesktop.resolve1.Manager',
                         in_signature='ia(sb)', out_signature='')
    def SetLinkDomains(self, interface_index: int, domains: list[(str, bool)]):
        lgr.info(f"SetLinkDomains called, interface index: {interface_index}, domains: {domains}")
        interface_cfg = self.interfaces.get(interface_index, InterfaceConfiguration(interface_index))
        interface_cfg.domains = [domain for domain, search in domains if not search]
        self.interfaces[interface_index] = interface_cfg

    @dbus.service.method(dbus_interface='org.freedesktop.resolve1.Manager',
                         in_signature='ib', out_signature='')
    def SetLinkDefaultRoute(self, interface_index: int, is_default: bool):
        lgr.info(f"SetLinkDefaultRoute called, interface index: {interface_index}, is_default: {is_default}")
        interface_cfg = self.interfaces.get(interface_index, InterfaceConfiguration(interface_index))
        interface_cfg.is_default = is_default
        self.interfaces[interface_index] = interface_cfg

    @dbus.service.method(dbus_interface='org.freedesktop.resolve1.Manager',
                         in_signature='is', out_signature='')
    def SetLinkLLMNR(self, interface_index: int, mode: str):
        # unbound does not support LLMNR
        lgr.info("SetLinkLLMNR called, and ignored")

    @dbus.service.method(dbus_interface='org.freedesktop.resolve1.Manager',
                         in_signature='is', out_signature='')
    def SetLinkMulticastDNS(self, interface_index: int, mode: str):
        # unbound does not support LLMNR
        lgr.info("SetLinkMulticastDNS called, and ignored")

    @dbus.service.method(dbus_interface='org.freedesktop.resolve1.Manager',
                         in_signature='is', out_signature='')
    def SetLinkDNSOverTLS(self, interface_index: int, mode: str):
        lgr.info(f"SetLinkDNSOverTLS called, interface index: {interface_index}, mode: {mode}")
        interface_cfg: InterfaceConfiguration = self.interfaces[interface_index]
        interface_cfg.dns_over_tls = True if mode == "yes" or mode == "opportunistic" else False
        # now let dns manager deal with update in its own way
        self.dns_mgr.update(self.interfaces)

    @dbus.service.method(dbus_interface='org.freedesktop.resolve1.Manager',
                         in_signature='is', out_signature='')
    def SetLinkDNSSEC(self, interface_index: int, mode: str):
        lgr.info(f"SetLinkDNSSEC called and ignored, interface index: {interface_index}, mode: {mode}")
        interface_cfg = self.interfaces.get(interface_index, InterfaceConfiguration(interface_index))
        interface_cfg.dns_over_tls = False if mode == "no" or mode == "allow-downgrade" else True
        self.interfaces[interface_index] = interface_cfg

    @dbus.service.method(dbus_interface='org.freedesktop.resolve1.Manager',
                         in_signature='ias', out_signature='')
    def SetLinkDNSSECNegativeTrustAnchors(self, interface_index: int, names: list[str]):
        lgr.info(f"SetLinkDNSSECNegativeTrustAnchors called and ignored, interface index: {interface_index}, names: {names}")

    @dbus.service.method(dbus_interface='org.freedesktop.resolve1.Manager',
                         in_signature='i', out_signature='')
    def RevertLink(self, interface_index: int):
        lgr.info(f"RevertLink called and ignored, interface index: {interface_index}")

