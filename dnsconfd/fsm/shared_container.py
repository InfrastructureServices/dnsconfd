from dnsconfd import SystemManager
from dnsconfd.fsm import ContextEvent, ExitCode
from dnsconfd.network_objects import ServerDescription, DnsProtocol, InterfaceConfiguration

import logging
import dbus
from typing import Callable, Any
import ipaddress
from gi.repository import GLib


class SharedContainer:
    def __init__(self, config: dict, main_loop, transition_function: Callable):
        self.config = config
        self.sys_mgr = SystemManager(config)
        self.main_loop = main_loop
        self.bus = None
        self.transition_function = transition_function
        self.lgr = logging.getLogger(self.__class__.__name__)
        self.static_servers = []
        self.handle_routes = config["handle_routing"]
        self.routes = {}
        self.wire_priority = config["prioritize_wire"]

        for resolver in config["static_servers"]:
            prot = resolver.get("protocol", None)
            if prot is not None:
                if prot == "plain":
                    prot = DnsProtocol.PLAIN
                elif prot == "DoT":
                    prot = DnsProtocol.DNS_OVER_TLS
            port = resolver.get("port", None)
            sni = resolver.get("sni", None)
            domains = resolver.get("domains", None)
            if domains is not None:
                transformed_domains = []
                for x in domains:
                    transformed_domains.append((x["domain"], x["search"]))
                domains = transformed_domains
            interface = resolver.get("interface", None)
            dnssec = resolver.get("dnssec", False)

            new_srv = ServerDescription.from_config(resolver["address"],
                                                    prot,
                                                    port,
                                                    sni,
                                                    domains,
                                                    interface,
                                                    dnssec)
            new_srv.priority = 150
            self.static_servers.append(new_srv)
        if len(self.static_servers) > 0:
            self.lgr.info(f"Configured static servers: {self.static_servers}")

        self._systemd_manager = None
        self._nm_interface = None
        self._signal_connection = None

        self.dns_mgr = None

        # dictionary, systemd jobs -> event that should be emitted on success,
        # event that should be emitted on failure
        self.systemd_jobs: dict[int, tuple[ContextEvent, ContextEvent]] = {}
        self.exit_code = 0
        self.servers: list[ServerDescription] = []

    def set_exit_code(self, code: ExitCode):
        if self.exit_code == 0:
            self.exit_code = code.value

    def get_zones_to_servers(self):
        new_zones_to_servers = {}

        search_domains = []

        for server in self.servers + self.static_servers:
            for domain, search in server.domains:
                try:
                    new_zones_to_servers[domain].append(server)
                except KeyError:
                    new_zones_to_servers[domain] = [server]
                if search:
                    search_domains.append(domain)

        for zone in new_zones_to_servers.keys():
            new_zones_to_servers[zone].sort(key=lambda x: x.priority,
                                            reverse=True)
        self.lgr.debug(f"New zones to server prepared: {new_zones_to_servers}")
        self.lgr.debug(f"New search domains prepared: {search_domains}")
        return new_zones_to_servers, search_domains

    def subscribe_systemd_signals(self):
        try:
            self._systemd_manager.Subscribe()
            connection = (self._systemd_manager.
                          connect_to_signal("JobRemoved",
                                            self.on_systemd_job_finished))
            self._signal_connection = connection
            return True
        except dbus.DBusException as e:
            self.lgr.error("Systemd is not listening on " +
                           f"name org.freedesktop.systemd1 {e}")
        return False

    def connect_systemd(self):
        try:
            self.bus = dbus.SystemBus()
            systemd_object = self.bus.get_object('org.freedesktop.systemd1',
                                                 '/org/freedesktop/systemd1')
            self._systemd_manager \
                = dbus.Interface(systemd_object,
                                 "org.freedesktop.systemd1.Manager")
            return True
        except dbus.DBusException as e:
            self.lgr.error("Systemd is not listening on name "
                           f"org.freedesktop.systemd1: {e}")
        return False

    def start_unit(self):
        self.lgr.info(f"Starting {self.dns_mgr.service_name}")
        try:
            name = f"{self.dns_mgr.service_name}.service"
            return int(self._systemd_manager
                       .ReloadOrRestartUnit(name,
                                            "replace").split('/')[-1])
        except dbus.DBusException as e:
            self.lgr.error("Was not able to call "
                           "org.freedesktop.systemd1.Manager"
                           f".ReloadOrRestartUnit , check your policy: {e}")
        return None

    def on_systemd_job_finished(self, *args):
        jobid = int(args[0])
        success_event, failure_event = self.systemd_jobs.pop(jobid,
                                                             (None, None))
        if success_event is not None:
            self.lgr.debug(f"{args[2]} start job finished")
            if not self.systemd_jobs:
                self.lgr.debug("Not waiting for more jobs, thus unsubscribing")
                # we do not want to receive info about jobs anymore
                self._systemd_manager.Unsubscribe()
                self._signal_connection.remove()
            if args[3] != "done" and args[3] != "skipped":
                self.lgr.error(f"{args[2]} unit failed to start, "
                               f"result: {args[3]}")
                self.transition_function(failure_event)
            self.transition_function(success_event)
        else:
            self.lgr.debug("Dnsconfd was informed about finish of"
                           f" job {jobid} but it was not submitted by us")

    def stop_unit(self):
        self.lgr.info(f"Stopping {self.dns_mgr.service_name}")
        try:
            name = f"{self.dns_mgr.service_name}.service"
            return int(self._systemd_manager
                       .StopUnit(name,
                                 "replace").split('/')[-1])
        except dbus.DBusException as e:
            self.lgr.error("Was not able to call "
                           "org.freedesktop.systemd1.Manager.StopUnit"
                           f", check your policy {e}")
        return None

    def handle_routes_process(self, event: ContextEvent):
        # we need to refresh the dbus connection, because NetworkManager
        # restart would invalidate it
        try:
            self._get_nm_interface()
        except dbus.DBusException as e:
            self.lgr.error("Failed to connect to NetworkManager through DBUS,"
                           f" {e}")
            self.set_exit_code(ExitCode.ROUTE_FAILURE)
            return ContextEvent("FAIL")

        interface_and_routes = []
        interface_to_connection = {}
        self.lgr.info("Commencing route check")

        found_interfaces = []

        for server in self.servers:
            if (server.interface is not None
                    and server.interface not in found_interfaces):
                found_interfaces.append(server.interface)

        for if_index in found_interfaces:
            ip4_rte, ip6_rte, applied = self._get_nm_device_config(if_index)
            if ip4_rte is None:
                self.set_exit_code(ExitCode.ROUTE_FAILURE)
                return ContextEvent("FAIL")
            elif applied is None:
                # we have to also remove routes of this interface,
                # so they do not interfere with further processing
                interface_servers = []
                for server in self.servers:
                    if server.interface == if_index:
                        interface_servers.append(server)
                for server in interface_servers:
                    self.routes.pop(server.get_server_string(), None)
                interface_to_connection[if_index] = None
                continue
            for route in ip4_rte + ip6_rte:
                interface_and_routes.append((if_index, route))
            interface_to_connection[if_index] = applied

        self.lgr.debug(f"interface and routes is {interface_and_routes}")
        self.lgr.debug("interface and connections "
                       f"is {interface_to_connection}")
        valid_routes = {}
        interface_names = []

        for x in found_interfaces:
            interface_names.append(InterfaceConfiguration.get_if_name(x))

        self.lgr.debug(f"interfaces are {interface_names}")

        interfaces_to_servers = {}
        for index in found_interfaces:
            interfaces_to_servers.setdefault(index, [])
        for server in self.servers:
            if server.interface is not None:
                interfaces_to_servers[server.interface].append(server)

        for int_index in found_interfaces:
            reapply_needed = False
            ifname = InterfaceConfiguration.get_if_name(int_index)
            if interface_to_connection[int_index] is None:
                # this will ensure that routes left after downed devices
                # are cleared
                continue
            connection = interface_to_connection[int_index][0]
            self._reset_bin_routes(connection)

            for server in interfaces_to_servers[int_index]:
                server_str = server.get_server_string()
                best_route = self._choose_best_route(server_str,
                                                     interface_and_routes)
                if best_route is None:
                    routing_right = False
                else:
                    routing_right = best_route[0] == int_index

                if (routing_right
                        and best_route[1]["dest"] not in self.routes.keys()):
                    self.lgr.debug("Routing is right, no additional action "
                                   "required continuing")
                    # this means that there is no additional action required
                    continue
                elif routing_right:
                    # routing is right, but chosen route has been submitted by
                    # us, and could have wrong gateway
                    self.lgr.debug("Routing is right, but the route was "
                                   "submitted by us, checking gateway")
                    def_route = None
                    cur_route = self.routes.get(str(best_route[1]["dest"]))

                    # find interface route with prefix 0, that will show us
                    # gateway
                    for (route_int_index, route) in interface_and_routes:
                        if (route_int_index == int_index
                                and route["prefix"] == 0
                                and "next-hop" in route.keys()):
                            def_route = (route_int_index, route)
                            break

                    if def_route is None:
                        self.lgr.info(
                            f"Could not find default route for {ifname} "
                            "and thus can not check submitted route")
                        valid_routes[str(best_route[1]["dest"])] = cur_route
                        continue
                    if def_route[1]["next-hop"] != best_route[1]["next-hop"]:
                        # change connection since there is a route created
                        # by us that is not right
                        self.lgr.debug("Gateway is not right, changing")
                        conn = interface_to_connection[int_index][0]
                        for family in ["ipv4", "ipv6"]:
                            for route in conn[family]["route-data"]:
                                if route["dest"] == best_route[1]["dest"]:
                                    route["next-hop"] = def_route[1]["next-hop"]
                                    dest = str(best_route[1]["dest"])
                                    valid_routes[dest] = route
                                    break
                        reapply_needed = True
                    else:
                        self.lgr.debug("Gateway is right continuing")
                        valid_routes[server_str] = cur_route
                else:
                    # routing is not right, and we must add route to fix
                    # the situation
                    duplicate = False
                    if best_route is not None:
                        for x in interfaces_to_servers[best_route[0]]:
                            # this is a bit of a problem, because using routes
                            # does not allow us to create separate rules
                            if x.address == server.address:
                                duplicate = True
                                break
                    if duplicate:
                        # different interface also should use this server, we
                        # should handle which one of them has priority
                        other_wireless = (
                            InterfaceConfiguration.
                            is_interface_wireless(best_route[0]))
                        this_wireless = (
                            InterfaceConfiguration.
                            is_interface_wireless(int_index))
                        other_name = (
                            InterfaceConfiguration.
                            get_if_name(best_route[0]))
                        if (self.wire_priority
                                and other_wireless
                                and not this_wireless):
                            self.lgr.info(f"Server {server_str} is listed by "
                                          f" both interfaces {ifname} and "
                                          f"{other_name} but since the latter "
                                          f"is wireless, {ifname} "
                                          "will be the one used")
                        else:
                            self.lgr.info(f"Server {server_str} is listed by "
                                          f"both interfaces {ifname} "
                                          f"and {other_name} "
                                          f"the latter will be used")
                            continue

                    self.lgr.debug("Adding route")
                    def_route = None
                    for (route_int_index, route) in interface_and_routes:
                        if (route_int_index == int_index
                                and route["prefix"] == 0
                                and "next-hop" in route.keys()):
                            def_route = (route_int_index, route)
                            break

                    if def_route is None:
                        self.lgr.info(
                            f"Could not find default route for {ifname} "
                            "and thus will not handle routing")
                        continue
                    self.lgr.debug(f"Default route is {def_route}")
                    dest_str = str(def_route[1]["dest"])
                    dest_ip = ipaddress.ip_address(dest_str)
                    new_route = dbus.Dictionary({
                        dbus.String("dest"):
                            dbus.String(server_str),
                        dbus.String("prefix"):
                            dbus.UInt32(dest_ip.max_prefixlen),
                        dbus.String("next-hop"):
                            dbus.String(def_route[1]["next-hop"])})

                    self.lgr.info(f"new route is {new_route}")
                    valid_routes[server_str] = new_route
                    if dest_ip.version == 4:
                        connection["ipv4"]["route-data"].append(new_route)
                    else:
                        connection["ipv6"]["route-data"].append(new_route)
                    reapply_needed = True
            if self._remove_checked_routes(connection, valid_routes):
                reapply_needed = True

            if reapply_needed:
                try:
                    cver = interface_to_connection[int_index][1]
                    self._reapply_routes(ifname, connection, cver)
                except dbus.DBusException as e:
                    self.lgr.error("Failed to reapply connection to "
                                   f"{ifname}, {e}")
                    self.set_exit_code(ExitCode.ROUTE_FAILURE)
                    return ContextEvent("FAIL")

        self.routes = valid_routes
        return ContextEvent("SUCCESS", data=event.data)

    def _remove_checked_routes(self,
                               connection: dict[str, dict[str, Any]],
                               valid_routes: dict | None) -> bool:
        modified = False
        for family in ["ipv4", "ipv6"]:
            for checked_route in list(connection[family]["route-data"]):
                if (str(checked_route["dest"]) in self.routes and
                    (valid_routes is None or
                     str(checked_route["dest"]) not in valid_routes)):
                    connection[family]["route-data"].remove(checked_route)
                    modified = True
                    self.lgr.info(f"Removing {family} route {checked_route}")
        return modified

    def _get_nm_device_interface(self, ifname):
        """Get DBus proxy object of Device identified by ifname."""
        device_path = self._nm_interface.GetDeviceByIpIface(ifname)
        self.lgr.debug(f"Device path is {device_path}")
        nm_int_str = "org.freedesktop.NetworkManager"
        dev_int_str = "org.freedesktop.NetworkManager.Device"
        device_object = self.bus.get_object(nm_int_str,
                                            device_path)
        dev_int = dbus.Interface(device_object,
                                 dev_int_str)
        return dev_int

    def _get_nm_interface(self):
        nm_dbus_name = "org.freedesktop.NetworkManager"
        nm_object = self.bus.get_object(nm_dbus_name,
                                        '/org/freedesktop/NetworkManager')
        self._nm_interface = dbus.Interface(nm_object,
                                            nm_dbus_name)
        return self._nm_interface

    def _reapply_routes(self, ifname, connection, cver):
        self.lgr.debug("Reapplying changed connection")
        self.lgr.info(f"New ipv4 route data "
                      f"{connection["ipv4"]["route-data"]}")
        self.lgr.info(f"New ipv6 route data "
                      f"{connection["ipv6"]["route-data"]}")
        dev_int = self._get_nm_device_interface(ifname)
        dev_int.Reapply(connection, cver, 0)

    @staticmethod
    def _reset_bin_routes(connection):
        # we need to remove this, so we can use route-data field
        # undocumented NetworkManager implementation detail
        del connection["ipv4"]["routes"]
        del connection["ipv6"]["routes"]

    def _get_nm_device_config(self, index):
        int_name = InterfaceConfiguration.get_if_name(index, strict=True)
        if int_name is None:
            self.lgr.info(f"interface {int_name} has no name and thus "
                          f"we will not handle its routing")
            return [], [], None
        self.lgr.debug(f"Getting NetworkManager info about {int_name}")
        try:
            device_path = self._nm_interface.GetDeviceByIpIface(int_name)
            self.lgr.debug(f"Device path is {device_path}")
            device_object = self.bus.get_object("org.freedesktop"
                                                ".NetworkManager",
                                                device_path)

            device_properties = dbus.Interface(device_object,
                                               "org.freedesktop"
                                               ".DBus.Properties").GetAll(
                "org.freedesktop.NetworkManager.Device")
            if not 80 <= device_properties["State"] <= 100:
                self.lgr.info(f"Interface {int_name} is not yet activated, "
                              f"state: {device_properties["State"]}, "
                              f"scheduling refresh")
                upd = ContextEvent("UPDATE")
                GLib.timeout_add_seconds(2,
                                         lambda: self.transition_function(upd))
                return [], [], None
            prop_interface = "org.freedesktop.DBus.Properties"
            ip4_object = self.bus.get_object('org.freedesktop.NetworkManager',
                                             device_properties["Ip4Config"])
            ip6_object = self.bus.get_object('org.freedesktop.NetworkManager',
                                             device_properties["Ip6Config"])
            ip4_routes = dbus.Interface(ip4_object,
                                        prop_interface).Get(
                "org.freedesktop.NetworkManager.IP4Config", "RouteData")
            self.lgr.info(f"ipv4 Route data is {ip4_routes}")
            ip6_routes = dbus.Interface(ip6_object,
                                        prop_interface).Get(
                "org.freedesktop.NetworkManager.IP6Config", "RouteData")
            self.lgr.info(f"ipv6 Route data is {ip6_routes}")
            ip4_addresses = dbus.Interface(ip4_object,
                                           prop_interface).Get(
                "org.freedesktop.NetworkManager.IP4Config", "Addresses")
            ip6_addresses = dbus.Interface(ip6_object,
                                           prop_interface).Get(
                "org.freedesktop.NetworkManager.IP6Config", "Addresses")
            if len(ip4_addresses) == 0 and len(ip6_addresses) == 0:
                self.lgr.info(f"interface {int_name} has no address "
                              "and thus we will not handle its routing")
                return [], [], None
            dev_int = dbus.Interface(device_object,
                                     "org.freedesktop.NetworkManager.Device")
            applied = dev_int.GetAppliedConnection(0)
            self.lgr.debug(f"Applied connection is {applied}")
        except dbus.DBusException as e:
            self.lgr.error(f"Failed to retrieve info about {int_name} "
                           "from NetworkManager")
            self.lgr.error(f"{e}")
            return None, None, None

        return ip4_routes, ip6_routes, applied

    def _choose_best_route(self, server_str, interface_and_routes):
        best_route = None
        server_ip = ipaddress.ip_address(server_str)
        self.lgr.debug(f"Handling server {server_str}")
        for (route_int_index, route) in interface_and_routes:
            net = ipaddress.ip_network(f"{route['dest']}/{route['prefix']}")
            if server_ip in net:
                if (best_route is None
                        or best_route[1]["prefix"] < route["prefix"]):
                    best_route = (route_int_index, route)
                elif (best_route[1]["prefix"] == route["prefix"]
                      and "metric" in best_route[1].keys()
                      and "metric" in route.keys()
                      and best_route[1]["metric"] > route["metric"]):
                    best_route = (route_int_index, route)
        self.lgr.debug(f"best route is {best_route}")
        return best_route

    def restart_unit(self):
        self.lgr.info(f"Restarting {self.dns_mgr.service_name}")
        try:
            name = f"{self.dns_mgr.service_name}.service"
            return int(self._systemd_manager
                       .RestartUnit(name, "replace").split('/')[-1])
        except dbus.DBusException as e:
            self.lgr.error("Was not able to call "
                           "org.freedesktop.systemd1.Manager.RestartUnit"
                           f", check your policy: {e}")
        return None

    def remove_routes(self):
        try:
            # we need to refresh the dbus connection, because NetworkManager
            # restart would invalidate it
            self._get_nm_interface()
        except dbus.DBusException:
            self.lgr.info("Failed to contact NetworkManager through dbus, "
                          "will not remove routes")
            return ContextEvent("SUCCESS")

        found_interfaces = []

        for server in self.servers:
            if (server.interface is not None
                    and server.interface not in found_interfaces):
                found_interfaces.append(server.interface)

        interfaces_to_servers = {}
        for index in found_interfaces:
            interfaces_to_servers.setdefault(index, [])
        for server in self.servers:
            interfaces_to_servers[server.interface].append(server)

        for int_index in found_interfaces:
            reapply_needed = False
            ifname = InterfaceConfiguration.get_if_name(int_index)
            try:
                dev_int = self._get_nm_device_interface(ifname)
                connection, cver = dev_int.GetAppliedConnection(0)
                self._reset_bin_routes(connection)
            except dbus.DBusException:
                self.lgr.info("Failed to retrieve info about interface "
                              f" {ifname}, Will not remove its routes")
                continue

            if self._remove_checked_routes(connection, None):
                reapply_needed = True

            if reapply_needed:
                try:
                    self._reapply_routes(ifname, connection, cver)
                except dbus.DBusException as e:
                    self.lgr.warning("Failed to reapply connection of "
                                     f"{ifname}, Will not remove its routes. "
                                     f"{e}")
                    continue
        return ContextEvent("SUCCESS")
