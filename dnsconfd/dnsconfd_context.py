from dnsconfd import SystemManager
from dnsconfd.configuration import InterfaceConfiguration
from dnsconfd.configuration import ServerDescription
from dnsconfd.dns_managers import UnboundManager

import signal
import logging as lgr
import sys
import json
import dbus.service
import socket


class DnsconfdContext(dbus.service.Object):
    def __init__(self, object_path, bus_name, config: dict):
        super().__init__(object_path=object_path, bus_name=bus_name)
        self.dns_mgr = None
        self.my_address = config["listen_address"]
        self.sys_mgr = SystemManager(config["resolv_conf_path"], self.my_address)
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
        self.dns_mgr.configure(self.my_address)
        self.dns_mgr.start()
        self.sys_mgr.setResolvconf()

    def log_servers(self, ifname: str, servers: list[ServerDescription]):
        """Log user friendly representation of servers."""
        nice_servers = ServerDescription.servers_string(servers)
        lgr.info(f"Incoming DNS servers on {ifname}: {nice_servers}")

    def ifprio(self, interface_cfg: InterfaceConfiguration):
        if interface_cfg.isInterfaceWireless():
            lgr.debug(f"Interface {interface_cfg.interface_index} is wireless")
            prio = 50
        else:
            prio = 100
        return prio

    def iface_config(self, interface_index: int):
        """Get existing or create new default interface configuration."""
        return self.interfaces.setdefault(interface_index, InterfaceConfiguration(interface_index))


    # From network manager code investigation it seems that these methods are called in
    # the following sequence: SetLinkDomains, SetLinkDefaultRoute, SetLinkMulticastDNS,
    # SetLinkLLMNR, SetLinkDNS, SetLinkDNSOverTLS
    # until proven otherwise, we will expect this to be true at all cases
    # but TODO ensure consistent state of service during partial updates

    # Implements systemd-resolved interfaces defined at:
    # https://www.freedesktop.org/software/systemd/man/latest/org.freedesktop.resolve1.html
    # or man 5 org.freedesktop.resolve1

    @dbus.service.method(dbus_interface='org.freedesktop.resolve1.Manager',
                         in_signature='ia(iay)', out_signature='')
    def SetLinkDNS(self, interface_index: int, addresses: list[(int, bytearray)]):
        lgr.debug(f"SetLinkDNS called, interface index: {interface_index}, addresses: {addresses}")
        interface_cfg = self.iface_config(interface_index)
        prio = self.ifprio(interface_cfg)
        servers = [ServerDescription(fam, addr, priority=prio) for fam, addr in addresses]
        interface_cfg.servers = servers
        self.log_servers(interface_cfg.ifname(), servers)

    @dbus.service.method(dbus_interface='org.freedesktop.resolve1.Manager',
                         in_signature='ia(iayqs)', out_signature='')
    def SetLinkDNSEx(self, interface_index: int, addresses: list[(int, bytearray, int, str)]):
        lgr.debug(f"SetLinkDNSEx called, interface index: {interface_index}, addresses: {addresses}")
        interface_cfg = self.iface_config(interface_index)
        prio = self.ifprio(interface_cfg)
        servers = [ServerDescription(fam, addr, port, sni, prio) for fam, addr, port, sni in addresses]
        interface_cfg.servers = servers
        self.log_servers(interface_cfg.ifname(), servers)

    @dbus.service.method(dbus_interface='org.freedesktop.resolve1.Manager',
                         in_signature='ia(sb)', out_signature='')
    def SetLinkDomains(self, interface_index: int, domains: list[(str, bool)]):
        lgr.debug(f"SetLinkDomains called, interface index: {interface_index}, domains: {domains}")
        interface_cfg = self.iface_config(interface_index)
        interface_cfg.domains = [(str(domain), bool(is_routing)) for domain, is_routing in domains]

    @dbus.service.method(dbus_interface='org.freedesktop.resolve1.Manager',
                         in_signature='ib', out_signature='')
    def SetLinkDefaultRoute(self, interface_index: int, is_default: bool):
        lgr.debug(f"SetLinkDefaultRoute called, interface index: {interface_index}, is_default: {is_default}")
        interface_cfg = self.iface_config(interface_index)
        interface_cfg.is_default = is_default

    @dbus.service.method(dbus_interface='org.freedesktop.resolve1.Manager',
                         in_signature='is', out_signature='')
    def SetLinkLLMNR(self, interface_index: int, mode: str):
        # unbound does not support LLMNR
        lgr.debug("SetLinkLLMNR called, and ignored")

    @dbus.service.method(dbus_interface='org.freedesktop.resolve1.Manager',
                         in_signature='is', out_signature='')
    def SetLinkMulticastDNS(self, interface_index: int, mode: str):
        lgr.debug("SetLinkMulticastDNS called, and ignored")

    @dbus.service.method(dbus_interface='org.freedesktop.resolve1.Manager',
                         in_signature='is', out_signature='')
    def SetLinkDNSOverTLS(self, interface_index: int, mode: str):
        lgr.debug(f"SetLinkDNSOverTLS called, interface index: {interface_index}, mode: '{mode}'")
        interface_cfg: InterfaceConfiguration = self.interfaces[interface_index]
        interface_cfg.dns_over_tls = True if mode == "yes" or mode == "opportunistic" else False
        # now let dns manager deal with update in its own way
        self._update()

    @dbus.service.method(dbus_interface='org.freedesktop.resolve1.Manager',
                         in_signature='is', out_signature='')
    def SetLinkDNSSEC(self, interface_index: int, mode: str):
        lgr.debug(f"SetLinkDNSSEC called and ignored, interface index: {interface_index}, mode: {mode}")
        interface_cfg = self.iface_config(interface_index)
        interface_cfg.dns_over_tls = False if mode == "no" or mode == "allow-downgrade" else True

    @dbus.service.method(dbus_interface='org.freedesktop.resolve1.Manager',
                         in_signature='ias', out_signature='')
    def SetLinkDNSSECNegativeTrustAnchors(self, interface_index: int, names: list[str]):
        lgr.debug(f"SetLinkDNSSECNegativeTrustAnchors called and ignored, interface index: {interface_index}, names: {names}")

    @dbus.service.method(dbus_interface='org.freedesktop.resolve1.Manager',
                         in_signature='i', out_signature='')
    def RevertLink(self, interface_index: int):
        lgr.debug(f"RevertLink called and ignored, interface index: {interface_index}")

    @dbus.service.method(dbus_interface='org.freedesktop.resolve1.Manager',
                         in_signature='', out_signature='')
    def FlushCaches(self):
        # TODO: we need ability to flush just a subtree, not always all records
        lgr.debug(f"FlushCaches called and ignored")

    @dbus.service.method(dbus_interface='org.freedesktop.resolve1.Dnsconfd',
                         in_signature='', out_signature='s')
    def Status(self):
        lgr.debug('Handling request for status')
        status = {}
        status["service"] = self.dns_mgr.service_name if self.dns_mgr is not None else ""
        status["config"] = self.dns_mgr.get_status() if self.dns_mgr is not None else ""
        return json.dumps(status)

    def _update(self):
        new_zones_to_servers = {}

        search_domains = []

        for interface in self.interfaces.values():
            lgr.debug(f"Processing interface {interface}")
            interface: InterfaceConfiguration
            this_interface_zones = [domain[0] for domain in interface.domains if domain[1]]
            search_domains.extend([domain[0] for domain in interface.domains if not domain[1]])
            if interface.is_default:
                lgr.debug("Interface is default, appending . as its zone")
                this_interface_zones.append(".")
            for zone in this_interface_zones:
                lgr.debug(f"Handling zone {zone} of the interface")
                new_zones_to_servers[zone] = new_zones_to_servers.get(zone, [])
                for server in interface.servers:
                    lgr.debug(f"Handling server {server}")
                    found_server = [a for a in new_zones_to_servers[zone] if server == a]
                    if len(found_server) > 0:
                        lgr.debug(f"Server {server} already in zone, handling priority")
                        found_server[0].priority = max(found_server.priority, server.priority)
                    else:
                        lgr.debug(f"Appending server {server} to zone {zone}")
                        new_zones_to_servers[zone].append(server)

        for zone in new_zones_to_servers.keys():
            new_zones_to_servers[zone].sort(key=lambda x: x.priority, reverse=True)

        self.sys_mgr.updateResolvconf(search_domains)
        self.dns_mgr.update(new_zones_to_servers)
