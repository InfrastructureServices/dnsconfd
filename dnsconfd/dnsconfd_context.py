from dnsconfd import SystemManager
from dnsconfd.configuration import InterfaceConfiguration
from dnsconfd.configuration import ServerDescription
from dnsconfd.dns_managers import UnboundManager

import signal
import logging as lgr
import json
import dbus.service
from gi.repository import GLib

class DnsconfdContext(dbus.service.Object):
    def __init__(self, config: dict):
        super().__init__(object_path="/org/freedesktop/resolve1",
                         bus_name=dbus.service.BusName(config["dbus_name"], dbus.SystemBus()))
        self.my_address = config["listen_address"]
        self.sys_mgr = SystemManager(config["resolv_conf_path"], self.my_address)
        self.interfaces: dict[InterfaceConfiguration] = {}
        self._main_loop = GLib.MainLoop()

        self._systemd_object = None

        self.dns_mgr = None

        # dictionary, systemd jobs -> manager instances of services they should start
        self._start_jobs = {}
        self._exit_code = 0

    def signal_handler(self, signum: int) -> int:
        """ Handle incoming signal and return appropriate exit code

        :param signum: signal integer representation
        :type signum: int
        :return: Exit code
        :rtype: int
        """
        lgr.info(f"Caught signal {signal.strsignal(signum)}, shutting down")
        return self.stop()

    def _stop_execution(self, exit_code):
        self._exit_code = exit_code
        self._main_loop.quit()

    def was_reload_requested(self) -> bool:
        """ Get whether reload was requested

        :return: True if reload was requested, otherwise False
        :rtype: bool
        """
        return self._exit_code == 256

    def _on_service_start_finished(self, *args):
        jobid = int(args[0])
        mgr_instance = self._start_jobs.pop(jobid, None)
        if mgr_instance is not None:
            lgr.debug(f"{args[2]} start job finished")
            if len(self._start_jobs.keys()) == 0:
                # we do not want to receive info about jobs anymore
                dbus.Interface(self._systemd_object,
                               "org.freedesktop.systemd1.Manager").Unsubscribe()
            if args[3] != "done" and args[3] != "skipped":
                lgr.error(f"{args[2]} unit failed to start, result: {args[3]}")
                self._stop_execution(1)
                return
            GLib.timeout_add_seconds(1, lambda: self._service_status_poll(mgr_instance))

    def _service_status_poll(self, mgr_instance: UnboundManager, counter = 0):
        # better way to find out whether service is ready was not found
        # TODO timeout or number of tries needs to be configurable here
        if not mgr_instance.is_ready():
            if counter == 3:
                lgr.error(f"{mgr_instance.service_name} did not respond in time, stopping dnsconfd")
                self._stop_execution(1)
                return False
            lgr.debug(f"{mgr_instance.service_name} still not ready, waiting")
            GLib.timeout_add_seconds(1,
                                     lambda: self._service_status_poll(mgr_instance,
                                                                       counter=counter+1))
        else:
            mgr_instance.start_finished = True
            self._update()
        # we need to return False so this event is removed from loop
        return False

    def _start_unit(self):
        lgr.info(f"Starting {self.dns_mgr.service_name}")
        interface = dbus.Interface(self._systemd_object, "org.freedesktop.systemd1.Manager")
        try:
            return int(interface.ReloadOrRestartUnit(f"{self.dns_mgr.service_name}.service",
                                                     "replace").split('/')[-1])
        except dbus.DBusException as e:
            lgr.error("Was not able to call org.freedesktop.systemd1.Manager.ReloadOrRestartUnit"
                      + ", check your policy")
            lgr.error(str(e))
        return None
        # start or restart service

    def _stop_unit(self):
        lgr.info(f"Stoping {self.dns_mgr.service_name}")
        interface = dbus.Interface(self._systemd_object, "org.freedesktop.systemd1.Manager")
        try:
            interface.StopUnit(f"{self.dns_mgr.service_name}.service", "replace")
            return True
        except dbus.DBusException as e:
            lgr.error("Was not able to call org.freedesktop.systemd1.Manager.StopUnit"
                      + ", check your policy")
            lgr.error(str(e))
        return False
        # stop service

    def _subscribe_systemd_signals(self):
        try:
            interface = dbus.Interface(self._systemd_object, "org.freedesktop.systemd1.Manager")
            interface.Subscribe()
            interface.connect_to_signal("JobRemoved", self._on_service_start_finished)
            return True
        except dbus.DBusException as e:
            lgr.error("Systemd is not listening on name org.freedesktop.systemd1")
            lgr.error(str(e))
        return False

    def _connect_systemd(self):
        try:
            self._systemd_object = dbus.SystemBus().get_object('org.freedesktop.systemd1',
                                                               '/org/freedesktop/systemd1')
            return True
        except dbus.DBusException as e:
            lgr.error("Systemd is not listening on name org.freedesktop.systemd1")
            lgr.error(str(e))
        return False

    def stop(self) -> int:
        """ Revert resolvconf changes and stop caching service

        :return: Exit code that should be used
        :rtype: int
        """
        if self.sys_mgr.resolvconf_altered:
            self.sys_mgr.revert_resolvconf()
        if not self._stop_unit():
            return 1
        return self._exit_code

    def start_service(self) -> bool:
        """ Perform preparation and start DNS caching service

        :return: True if success, otherwise False
        :rtype: bool
        """
        if not self._connect_systemd() or not self._subscribe_systemd_signals():
            return False
        # TODO we will configure this in configuration
        self.dns_mgr = UnboundManager()
        self.dns_mgr.configure(self.my_address)
        service_start_job = self._start_unit()
        if service_start_job is None:
            return False
        self._start_jobs[service_start_job] = self.dns_mgr
        # end of part that will be configured
        self.sys_mgr.setResolvconf()
        return True

    def process_events(self):
        self._main_loop.run()

    def _log_servers(self, ifname: str, servers: list[ServerDescription]):
        """ Log string representation of list of ServerDescription instances

        :param ifname: Name of interface associated with servers
        :type ifname: str
        :param servers: list of server descriptions associated with the interface
        :type servers: list[ServerDescription]
        """
        nice_servers = ServerDescription.servers_string(servers)
        lgr.info(f"Incoming DNS servers on {ifname}: {nice_servers}")

    def _ifprio(self, interface_cfg: InterfaceConfiguration) -> int:
        if interface_cfg.is_interface_wireless():
            lgr.debug(f"Interface {interface_cfg.interface_index} is wireless")
            return 50
        return 100

    def _iface_config(self, interface_index: int):
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
        interface_cfg = self._iface_config(interface_index)
        prio = self._ifprio(interface_cfg)
        servers = [ServerDescription(fam, addr, priority=prio) for fam, addr in addresses]
        interface_cfg.servers = servers
        self._log_servers(interface_cfg.get_ifname(), servers)

    @dbus.service.method(dbus_interface='org.freedesktop.resolve1.Manager',
                         in_signature='ia(iayqs)', out_signature='')
    def SetLinkDNSEx(self, interface_index: int, addresses: list[(int, bytearray, int, str)]):
        lgr.debug(f"SetLinkDNSEx called, interface index: {interface_index}, addresses: {addresses}")
        interface_cfg = self._iface_config(interface_index)
        prio = self._ifprio(interface_cfg)
        servers = [ServerDescription(fam, addr, port, sni, prio) for fam, addr, port, sni in addresses]
        interface_cfg.servers = servers
        self._log_servers(interface_cfg.get_ifname(), servers)

    @dbus.service.method(dbus_interface='org.freedesktop.resolve1.Manager',
                         in_signature='ia(sb)', out_signature='')
    def SetLinkDomains(self, interface_index: int, domains: list[(str, bool)]):
        lgr.debug(f"SetLinkDomains called, interface index: {interface_index}, domains: {domains}")
        interface_cfg = self._iface_config(interface_index)
        interface_cfg.finished = False
        interface_cfg.domains = [(str(domain), bool(is_routing)) for domain, is_routing in domains]

    @dbus.service.method(dbus_interface='org.freedesktop.resolve1.Manager',
                         in_signature='ib', out_signature='')
    def SetLinkDefaultRoute(self, interface_index: int, is_default: bool):
        lgr.debug(f"SetLinkDefaultRoute called, interface index: {interface_index}, is_default: {is_default}")
        interface_cfg = self._iface_config(interface_index)
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
        interface_cfg.finished = True
        # zero keys in start jobs means that we consider unbound healthy and running
        if self.dns_mgr.start_finished:
            # now let dns manager deal with update in its own way
            self._update()
        else:
            lgr.info("A service start job is running, derefering update")

    @dbus.service.method(dbus_interface='org.freedesktop.resolve1.Manager',
                         in_signature='is', out_signature='')
    def SetLinkDNSSEC(self, interface_index: int, mode: str):
        lgr.debug(f"SetLinkDNSSEC called and ignored, interface index: {interface_index}, mode: {mode}")
        interface_cfg = self._iface_config(interface_index)
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
        lgr.debug("Handling request for status")
        status = {"service": self.dns_mgr.service_name, "config": self.dns_mgr.get_status()}
        return json.dumps(status)

    @dbus.service.method(dbus_interface='org.freedesktop.resolve1.Dnsconfd',
                         in_signature='s', out_signature='')
    def Reload(self, plugin: str):
        lgr.info(f"Received request for reload{' of plugin ' + plugin if plugin != '' else ''}")
        if plugin == self.dns_mgr.service_name:
            if not self.dns_mgr.start_finished:
                lgr.info("Plugin does not allow reload at this time")
                return
            self._reload_plugin()
        elif plugin != '':
            lgr.warning("Plugin is not currently active and thus can not be reloaded")
        else:
            # exit codes can be 0-255 that means 256 can be our internal value informing
            # loop about reload request
            self._stop_execution(256)

    def _reload_plugin(self):
        self.dns_mgr.clear_state()
        GLib.timeout_add_seconds(1, lambda: self._service_status_poll(self.dns_mgr))

    def _update(self):
        for config in self.interfaces.values():
            if not config.finished:
                lgr.debug("Not all interfaces are complete, derefering update")
                return
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

        self.sys_mgr.update_resolvconf(search_domains)
        self.dns_mgr.update(new_zones_to_servers)
