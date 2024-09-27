import ipaddress
import logging
import traceback
from typing import Any, Callable

import dbus

from dnsconfd.fsm import ContextEvent
from dnsconfd.network_objects import ServerDescription, InterfaceConfiguration


class RoutingManager:
    def __init__(self, wire_priority: bool, transition_function: Callable):

        self._nm_interface = None
        self.lgr = logging.getLogger(self.__class__.__name__)

        self.routes = {}

        self.wire_priority = wire_priority

        self.interface_to_state_signal_connection = {}
        self.interfaces_up = {}

        self.interface_ip_ready = {}
        self.interface_to_ip_signal_connections = {}

        self.state_serial = 0
        self.ip_serial = 0
        self.dhcp_serial = 0
        self.transition_function = transition_function

        self.interface_to_connection = {}

        # interface -> (ip_dict, is_ready_bool)
        self.required_dhcp4 = {}
        self.required_dhcp6 = {}

        self.dhcp_objs_signal_connections = []

    @staticmethod
    def _serial_add(serial):
        return serial + 1 if serial < 1000 else 0

    def change_serials(self, state_serial: bool, ip_serial: bool, dhcp_serial: bool):
        if state_serial:
            self.state_serial = self._serial_add(self.state_serial)
        if ip_serial:
            self.ip_serial = self._serial_add(self.ip_serial)
        if dhcp_serial:
            self.dhcp_serial = self._serial_add(self.dhcp_serial)

    def are_all_up(self):
        for interface in self.interfaces_up:
            if not self.interfaces_up[interface]:
                return False
        return True

    def on_device_state_changed(self, serial, interface, new_state, old_state, reason):
        # it is possible, that dbus event was already dispatched
        # that belonged to previous update, and we need to ensure
        # this will be ignored, since we can not remove them
        if self.state_serial != serial:
            return
        if new_state == 100:
            self.interfaces_up[interface] = True
            self.lgr.info("Interface up event on interface %s", interface)
            self.lgr.debug("State was %s reason %s", new_state, reason)
            self.transition_function(ContextEvent("INTERFACE_UP",
                                                  interface))
        elif old_state == 100 and new_state != 100:
            self.interfaces_up[interface] = False
            self.lgr.info("Interface down event on interface %s", interface)
            self.lgr.debug("State was %s reason %s", new_state, reason)
            self.transition_function(ContextEvent("INTERFACE_DOWN",
                                                  interface))

    def check_ip_object_ready(self, ip_object, interface, family):
        for route, route_interface in self.routes.values():
            if route_interface != interface:
                continue
            parsed_dest = ipaddress.ip_address((route["dest"]))
            if parsed_dest.version != family:
                continue
            route_found = False
            if "RouteData" not in ip_object:
                return False
            for obj_route in ip_object["RouteData"]:
                if ("next-hop" in obj_route
                        and parsed_dest == ipaddress.ip_address(obj_route["dest"])
                        and ipaddress.ip_address(obj_route["next-hop"]) == ipaddress.ip_address(route["next-hop"])):
                    route_found = True
                    break
            if not route_found:
                self.lgr.debug(f"interface {interface} family {family} ip object is not ready because it has not route")
                self.lgr.debug(f"{route["dest"]}")
                self.lgr.debug(f"ip object {ip_object}")
                self.lgr.debug(f"routes: {self.routes}")
                return False
        return True

    def on_ip_obj_change(self, cur_serial: int, interface: int, properties: dict, family: int):
        self.lgr.debug(f"ON IP UPDATE {properties}")
        if self.ip_serial != cur_serial or "RouteData" not in properties:
            self.lgr.debug("DENIED")
            return
        if self.check_ip_object_ready(properties, interface, family):
            if family == 4:
                self.interface_ip_ready[interface] = True, self.interface_ip_ready[interface][1]
            else:
                self.interface_ip_ready[interface] = self.interface_ip_ready[interface][0], True
            self.transition_function(ContextEvent("IP_SET"))
        else:
            if family == 4:
                self.interface_ip_ready[interface] = False, self.interface_ip_ready[interface][1]
            else:
                self.interface_ip_ready[interface] = self.interface_ip_ready[interface][0], True
            self.transition_function(ContextEvent("IP_UNSET"))

    def are_all_ip_set(self):
        self.lgr.debug(f"{self.interface_ip_ready} interface HERE")
        for interface, booleans in self.interface_ip_ready.items():
            if not (booleans[0] and booleans[1]):
                return False
        return True

    def subscribe_to_ip_objs_change(self, interfaces: list[int]):
        try:
            self._get_nm_interface()
        except dbus.DBusException as e:
            self.lgr.debug("Could not connect to nm in subscribe_to_ip_objs_change")
            return False
        for interface in interfaces:
            int_name = InterfaceConfiguration.get_if_name(interface, strict=True)
            if int_name is None:
                self.lgr.debug("Could not get interface name in subscribe_to_device_state_change")
                return False
            try:
                device_path = self._nm_interface.GetDeviceByIpIface(int_name)
                self.lgr.debug(f"Device path is {device_path}")
                device_object = dbus.SystemBus().get_object("org.freedesktop"
                                                            ".NetworkManager",
                                                            device_path)
                device_properties = dbus.Interface(device_object,
                                                   "org.freedesktop"
                                                   ".DBus.Properties").GetAll(
                    "org.freedesktop.NetworkManager.Device")

                ip4_config_path = device_properties["Ip4Config"]
                ip6_config_path = device_properties["Ip6Config"]
                ip4_config_object = dbus.SystemBus().get_object("org.freedesktop.NetworkManager", ip4_config_path)
                ip6_config_object = dbus.SystemBus().get_object("org.freedesktop.NetworkManager", ip6_config_path)

                cur_serial = self.ip_serial

                ip4_interface = dbus.Interface(ip4_config_object, "org.freedesktop.DBus.Properties")
                ip6_interface = dbus.Interface(ip6_config_object, "org.freedesktop.DBus.Properties")

                ip4_connection = ip4_interface.connect_to_signal("PropertiesChanged",
                                                                 lambda interface_str, properties, invalidated: self.on_ip_obj_change(cur_serial,
                                                                                                          interface,
                                                                                                          properties,
                                                                                                          4))
                self.interface_to_ip_signal_connections[interface] = (ip4_connection, None)
                ip6_connection = ip6_interface.connect_to_signal("PropertiesChanged",
                                                                 lambda interface_str, properties, invalidated: self.on_ip_obj_change(cur_serial,
                                                                                                          interface,
                                                                                                          properties,
                                                                                                          6))
                self.interface_to_ip_signal_connections[interface] = (ip4_connection, ip6_connection)

                ip4_properties = dbus.Interface(ip4_config_object,
                                                "org.freedesktop"
                                                ".DBus.Properties").GetAll(
                    "org.freedesktop.NetworkManager.IP4Config")

                ip6_properties = dbus.Interface(ip6_config_object,
                                                "org.freedesktop"
                                                ".DBus.Properties").GetAll(
                    "org.freedesktop.NetworkManager.IP6Config")

                self.lgr.debug(f"IP PROPERTIES IS {ip4_properties} {ip6_properties}")

                ip4_ready = self.check_ip_object_ready(ip4_properties, interface, 4)
                ip6_ready = self.check_ip_object_ready(ip6_properties, interface, 6)

                self.interface_ip_ready[interface] = (ip4_ready, ip6_ready)

            except dbus.DBusException:
                return False
        return True

    def subscribe_to_device_state_change(self, interfaces: list[int]):
        try:
            self._get_nm_interface()
        except dbus.DBusException as e:
            self.lgr.debug("Could not connect to nm in subscribe_to_device_state_change")
            return False
        for interface in interfaces:
            int_name = InterfaceConfiguration.get_if_name(interface, strict=True)
            if int_name is None:
                self.lgr.debug("Could not get interface name in subscribe_to_device_state_change")
                return False
            try:
                device_path = self._nm_interface.GetDeviceByIpIface(int_name)
                self.lgr.debug(f"Device path is {device_path}")
                device_object = dbus.SystemBus().get_object("org.freedesktop"
                                                            ".NetworkManager",
                                                            device_path)
                device_interface = dbus.Interface(device_object, "org.freedesktop.NetworkManager.Device")
                cur_serial = self.state_serial
                self.interface_to_state_signal_connection[interface] = device_interface.connect_to_signal(
                    "StateChanged",
                    lambda new_state,
                           old_state,
                           reason: self.on_device_state_changed(
                        cur_serial,
                        interface,
                        new_state,
                        old_state,
                        reason))
                device_properties = dbus.Interface(device_object,
                                                   "org.freedesktop"
                                                   ".DBus.Properties").GetAll(
                    "org.freedesktop.NetworkManager.Device")
                self.interfaces_up[interface] = device_properties["State"] == 100
                self.lgr.debug("Interface %s state %s during subscription", interface, device_properties["State"])
            except dbus.DBusException:
                return False
        return True

    def clear_subscriptions(self):
        self.change_serials(True, True, True)
        self.interfaces_up = {}
        for interface in self.interface_to_state_signal_connection:
            self.interface_to_state_signal_connection[interface].remove()
        self.interface_ip_ready = {}
        for interface in self.interface_to_ip_signal_connections:
            self.interface_to_ip_signal_connections[interface][0].remove()
            if self.interface_to_ip_signal_connections[interface][1]:
                self.interface_to_ip_signal_connections[interface][1].remove()
        self.interface_to_connection = {}

        for conn in self.dhcp_objs_signal_connections:
            conn.remove()
        self.required_dhcp4 = {}
        self.required_dhcp6 = {}

    def clear_ip_subscriptions(self):
        self.change_serials(False, True, False)
        self.interface_ip_ready = {}
        for interface in self.interface_to_ip_signal_connections:
            self.interface_to_ip_signal_connections[interface][0].remove()
            if self.interface_to_ip_signal_connections[interface][1]:
                self.interface_to_ip_signal_connections[interface][1].remove()

    def check_all_dhcp_ready(self):
        for dhcp_dict in self.required_dhcp4.values():
            if "ip_address" not in dhcp_dict:
                return False
        for dhcp_dict in self.required_dhcp6.values():
            if "ip_address" not in dhcp_dict:
                return False
        return True

    def _on_dhcp_change(self, serial, option_dict, interface, family):
        if serial != self.dhcp_serial:
            return
        if family == 4:
            self.required_dhcp4[interface] = option_dict
        else:
            self.required_dhcp6[interface] = option_dict
        self.transition_function(ContextEvent("DHCP_CHANGE"))

    def subscribe_required_dhcp(self):
        try:
            self._get_nm_interface()
        except dbus.DBusException as e:
            self.lgr.debug("Could not connect to nm in subscribe_to_ip_objs_change")
            return False
        for interface in self.required_dhcp4:
            int_name = InterfaceConfiguration.get_if_name(interface, strict=True)
            if int_name is None:
                self.lgr.debug("Could not get interface name in subscribe_required_dhcp")
                return False
            try:
                device_path = self._nm_interface.GetDeviceByIpIface(int_name)
                self.lgr.debug(f"Device path is {device_path}")
                device_object = dbus.SystemBus().get_object("org.freedesktop"
                                                            ".NetworkManager",
                                                            device_path)
                device_properties = dbus.Interface(device_object,
                                                   "org.freedesktop"
                                                   ".DBus.Properties").GetAll(
                    "org.freedesktop.NetworkManager.Device")

                dhcp4_config_path = device_properties["Dhcp4Config"]
                dhcp4_config_object = dbus.SystemBus().get_object("org.freedesktop.NetworkManager", dhcp4_config_path)

                cur_serial = self.dhcp_serial

                dhcp4_interface = dbus.Interface(dhcp4_config_object, "org.freedesktop.DBus.Properties")

                dhcp4_connection = dhcp4_interface.connect_to_signal("PropertiesChanged",
                                                                     lambda interface_str, properties, invalidated: self._on_dhcp_change(cur_serial, properties["Options"], interface, 4))
                self.dhcp_objs_signal_connections.append(dhcp4_connection)
                dhcp4_properties = dbus.Interface(dhcp4_config_object,
                                                  "org.freedesktop"
                                                  ".DBus.Properties").GetAll(
                    "org.freedesktop.NetworkManager.DHCP4Config")

                self.required_dhcp4[interface] = dhcp4_properties["Options"]
            except dbus.DBusException:
                return False

        for interface in self.required_dhcp6:
            int_name = InterfaceConfiguration.get_if_name(interface, strict=True)
            if int_name is None:
                self.lgr.debug("Could not get interface name in subscribe_required_dhcp")
                return False
            try:
                device_path = self._nm_interface.GetDeviceByIpIface(int_name)
                self.lgr.debug(f"Device path is {device_path}")
                device_object = dbus.SystemBus().get_object("org.freedesktop"
                                                            ".NetworkManager",
                                                            device_path)
                device_properties = dbus.Interface(device_object,
                                                   "org.freedesktop"
                                                   ".DBus.Properties").GetAll(
                    "org.freedesktop.NetworkManager.Device")

                dhcp6_config_path = device_properties["Dhcp6Config"]
                dhcp6_config_object = dbus.SystemBus().get_object("org.freedesktop.NetworkManager",
                                                                  dhcp6_config_path)

                cur_serial = self.dhcp_serial

                dhcp6_interface = dbus.Interface(dhcp6_config_object, "org.freedesktop.DBus.Properties")

                dhcp6_connection = dhcp6_interface.connect_to_signal("PropertiesChanged",
                                                                     lambda interface_str, properties, invalidated: self._on_dhcp_change(cur_serial, properties["Options"], interface, 6))
                self.dhcp_objs_signal_connections.append(dhcp6_connection)
                dhcp6_properties = dbus.Interface(dhcp6_config_object,
                                                  "org.freedesktop"
                                                  ".DBus.Properties").GetAll(
                    "org.freedesktop.NetworkManager.DHCP6Config")

                self.required_dhcp6[interface] = dhcp6_properties["Options"]
            except dbus.DBusException:
                return False
        return True

    def gather_connections(self, interfaces):
        try:
            self._get_nm_interface()
        except dbus.DBusException as e:
            self.lgr.warning("Failed to connect to NetworkManager through DBUS, routing will result when all "
                             f"interfaces are ready {e}")
            return False

        for if_index in interfaces:
            applied = self._get_nm_device_config(if_index)
            if applied is None:
                # All interfaces must be ready, otherwise routing can not be complete
                self.lgr.debug("All interfaces were not ready to gather connections")
                return False
            self.interface_to_connection[if_index] = applied
            if str(applied[0]["ipv4"]["method"]) == "auto":
                self.required_dhcp4[if_index] = {}
            if str(applied[0]["ipv6"]["method"]) == "auto":
                self.required_dhcp6[if_index] = {}
        return True

    def handle_routes_process(self, servers: list[ServerDescription]):
        # we need to refresh the dbus connection, because NetworkManager
        # restart would invalidate it
        try:
            self._get_nm_interface()
        except dbus.DBusException as e:
            self.lgr.warning("Failed to connect to NetworkManager through DBUS, routing will result when all "
                             f"interfaces are ready {e}")
            return False

        interface_to_connection = self.interface_to_connection
        self.lgr.info("Commencing route check")

        found_interfaces = self.interface_to_connection.keys()

        self.lgr.debug("interface and connections "
                       f"is {interface_to_connection}")
        interface_names = []

        for x in found_interfaces:
            interface_names.append(InterfaceConfiguration.get_if_name(x))

        self.lgr.debug(f"interfaces are {interface_names}")

        interfaces_to_servers = {}
        for index in found_interfaces:
            interfaces_to_servers.setdefault(index, [])
        for server in servers:
            if server.interface is not None:
                interfaces_to_servers[server.interface].append(server)

        for int_index in found_interfaces:
            valid_routes = {}
            reapply_needed = False
            ifname = InterfaceConfiguration.get_if_name(int_index)

            connection = interface_to_connection[int_index][0]
            self._reset_bin_routes(connection)

            for server in interfaces_to_servers[int_index]:
                server_str = server.get_server_string()
                parsed_server_str = ipaddress.ip_address(server_str)
                connection_existing_route = None
                connection_existing_backup_route = None
                dhcp_existing_route = False
                dhcp_existing_backup_route = False
                same_network = False
                ip_dict = connection["ipv4" if parsed_server_str.version == 4 else "ipv6"]
                dhcp_address_network = None
                dhcp_gateway_str = None
                dhcp_routes = []

                if ip_dict["method"] == "auto":
                    if parsed_server_str.version == 4:
                        addr_str = self.required_dhcp4[int_index]["ip_address"]
                        addr_mask = self.required_dhcp4[int_index]["subnet_mask"]
                        if "routers" in self.required_dhcp4[int_index]:
                            dhcp_gateway_str = self.required_dhcp4[int_index]["routers"].split()[0]
                        if "static_routes" in self.required_dhcp4[int_index]:
                            dhcp_routes = self.required_dhcp4[int_index]["static_routes"].split()
                    else:
                        addr_str = self.required_dhcp6[int_index]["ip_address"]
                        addr_mask = self.required_dhcp6[int_index]["subnet_mask"]
                        if "routers" in self.required_dhcp6[int_index]:
                            dhcp_gateway_str = self.required_dhcp6[int_index]["routers"].split()[0]
                        if "static_routes" in self.required_dhcp6[int_index]:
                            dhcp_routes = self.required_dhcp6[int_index]["static_routes"].split()
                    dhcp_address_network = ipaddress.ip_network(f"{addr_str}/{addr_mask}", strict=False)

                for addr in ip_dict["address-data"]:
                    if parsed_server_str in ipaddress.ip_network(f"{addr["address"]}/{addr["prefix"]}", strict=False):
                        same_network = True
                if not same_network and dhcp_address_network and parsed_server_str in dhcp_address_network:
                    same_network = True

                if same_network:
                    self.lgr.info("Server %s is in local network, routing not needed", server_str)
                    continue

                for route in ip_dict["route-data"]:
                    if "dest" in route and ipaddress.ip_address(route["dest"]) == parsed_server_str and "prefix" in route and route["prefix"] == parsed_server_str.max_prefixlen:
                        connection_existing_route = route
                        break
                for route in ip_dict["route-data"]:
                    if "dest" in route and "prefix" in route and "next-hop" in route and parsed_server_str in ipaddress.ip_network(f"{route["dest"]}/{route["prefix"]}"):
                        connection_existing_backup_route = route
                        break
                if dhcp_routes and not connection_existing_route:
                    for dest_str, next_hop_str in zip(dhcp_routes[0::2], dhcp_routes[1::2]):
                        parsed = ipaddress.ip_network(dest_str, strict=False)
                        if parsed.prefixlen == parsed.max_prefixlen and parsed.network_address == parsed_server_str:
                            dhcp_existing_route = (parsed.network_address, ipaddress.ip_address(next_hop_str))
                        elif parsed_server_str in parsed:
                            dhcp_existing_backup_route = (parsed.network_address, ipaddress.ip_address(next_hop_str))

                nexthop_right = False
                next_hop = None
                if connection_existing_route:
                    next_hop = connection_existing_route.get("next-hop", None)

                gateway_in_connection = "gateway" in ip_dict
                if next_hop:
                    if gateway_in_connection and ipaddress.ip_address(next_hop) == ipaddress.ip_address(
                            ip_dict["gateway"]):
                        nexthop_right = True
                    elif dhcp_gateway_str and ipaddress.ip_address(next_hop) == ipaddress.ip_address(dhcp_gateway_str):
                        nexthop_right = True

                if connection_existing_route and nexthop_right:
                    if server_str in self.routes:
                        # route was submitted by us and it is valid
                        valid_routes[server_str] = (connection_existing_route, int_index)
                    self.lgr.debug("Routing is right, no additional action "
                                   "required continuing")
                    # this means that there is no additional action required
                    continue
                elif connection_existing_route:
                    if server_str in self.routes:
                        if not (gateway_in_connection or dhcp_gateway_str) and connection_existing_backup_route:
                            if ipaddress.ip_address(connection_existing_route["next-hop"]) != ipaddress.ip_address(connection_existing_backup_route["next-hop"]):
                                self.lgr.info("Route exists but the nexthop is not right, to the original broader route from connection, will change it")
                                connection_existing_route["next-hop"] = connection_existing_backup_route["next-hop"]
                            else:
                                self.lgr.info("Route exists and it is correct according to broader route from connection")
                                continue
                        elif not (gateway_in_connection or dhcp_gateway_str) and dhcp_existing_backup_route:
                            if ipaddress.ip_address(connection_existing_route["next-hop"]) != dhcp_existing_backup_route[1]:
                                self.lgr.info("Route exists but the nexthop is not right, to the original broader route from DHCP, will change it")
                                connection_existing_route["next-hop"] = dbus.String(str(dhcp_existing_backup_route[1]))
                            else:
                                self.lgr.info("Route exists and it is correct according to broader route from DHCP")
                                continue
                        elif gateway_in_connection or dhcp_gateway_str:
                            self.lgr.info("Route exists but the nexthop is not right, will change it")
                            connection_existing_route["next-hop"] = ip_dict["gateway"] if gateway_in_connection else dbus.String(dhcp_gateway_str)
                        else:
                            self.lgr.error(
                                "Route exists but the nexthop is not right and default gateway is not set, waiting for it to be set")
                            return False
                    else:
                        self.lgr.warning(
                            "Route exists but the nexthop is not right and it was not submitted by us, relying on your network configuration")
                        continue

                    valid_routes[server_str] = (connection_existing_route, int_index)
                    reapply_needed = True
                elif dhcp_existing_route:
                    self.lgr.warning("Route exists, but it was received through DHCP, relying on your network configuration")
                    continue
                else:
                    if gateway_in_connection or dhcp_gateway_str:
                        self.lgr.debug("Route does not exist, creating it")
                        gateway_dbus_string = ip_dict["gateway"] if gateway_in_connection else dbus.String(
                            dhcp_gateway_str)
                    elif connection_existing_backup_route:
                        self.lgr.debug("Route does not exist, however there is route in connection that would contain this server, will create its specified version")
                        gateway_dbus_string = connection_existing_backup_route["next-hop"]
                    elif dhcp_existing_backup_route:
                        self.lgr.debug(
                            "Route does not exist, however there is route gotten through DHCP that would contain this server, will create its specified version")
                        gateway_dbus_string = dbus.String(str(dhcp_existing_backup_route[1]))
                    else:
                        self.lgr.error("Route does not exist, and gateway is not set, waiting until it is")
                        return False

                    new_route = dbus.Dictionary({
                        dbus.String("dest"):
                            dbus.String(server_str),
                        dbus.String("prefix"):
                            dbus.UInt32(parsed_server_str.max_prefixlen),
                        dbus.String("next-hop"):
                            gateway_dbus_string})
                    valid_routes[server_str] = (new_route, int_index)
                    if parsed_server_str.version == 4:
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
                    return False
                for destination in list(self.routes):
                    if self.routes[destination][1] == int_index:
                        self.routes.pop(destination)
                # worth noting that i thought of a server changing interfaces
                # and thus having route elsewhere, but since side effect of
                # _remove_checked_routes is that if the route exists and
                # is not valid for the certain interface then it also will
                # be removed from that connection even if the route is valid
                # for other connection
                self.routes.update(valid_routes)

        # now if there are routes in self.routes for interfaces that are
        # not in found_interfaces, that means that there are either
        # bogus routes or those interfaces were downed thus
        # walk them, remove bogus routes and then delete them from
        # self.routes
        downed_interfaces = []
        for route, interface in list(self.routes.values()):
            if interface not in found_interfaces and interface not in downed_interfaces:
                downed_interfaces.append(interface)
                int_name = InterfaceConfiguration.get_if_name(interface, strict=True)
                if int_name is not None:
                    try:
                        device_path = self._nm_interface.GetDeviceByIpIface(int_name)
                        self.lgr.debug(f"Device path is {device_path}")
                        device_object = dbus.SystemBus().get_object("org.freedesktop"
                                                                    ".NetworkManager",
                                                                    device_path)
                        device_properties = dbus.Interface(device_object,
                                                           "org.freedesktop"
                                                           ".DBus.Properties").GetAll(
                            "org.freedesktop.NetworkManager.Device")
                        if device_properties["State"] == 100:
                            ip4_rte, ip6_rte, applied = self._get_nm_device_config(interface)
                            if self._remove_checked_routes(applied[0], None):
                                self._reapply_routes(int_name, applied[0], applied[1])
                    except dbus.DBusException:
                        self.lgr.debug("Failed to clean interface %s", downed_interfaces)
                        return False
                for destination in list(self.routes):
                    if self.routes[destination][1] == interface:
                        self.routes.pop(destination)

        return True

    # TODO Ensure the same server can not have 2 interfaces

    def _remove_checked_routes(self,
                               connection: dict[str, dict[str, Any]],
                               valid_routes: dict | None) -> bool:
        modified = False
        for family in ["ipv4", "ipv6"]:
            for checked_route in list(connection[family]["route-data"]):
                if (str(checked_route["dest"]) in self.routes
                        and (valid_routes is None
                             or str(checked_route["dest"]) not in valid_routes)):
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
        device_object = dbus.SystemBus().get_object(nm_int_str,
                                                    device_path)
        dev_int = dbus.Interface(device_object,
                                 dev_int_str)
        return dev_int

    def _get_nm_interface(self):
        nm_dbus_name = "org.freedesktop.NetworkManager"
        nm_object = dbus.SystemBus().get_object(nm_dbus_name,
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
                          f"we will not handle its routing now")
            return None
        self.lgr.debug(f"Getting NetworkManager info about {int_name}")
        try:
            device_path = self._nm_interface.GetDeviceByIpIface(int_name)
            self.lgr.debug(f"Device path is {device_path}")
            device_object = dbus.SystemBus().get_object("org.freedesktop"
                                                        ".NetworkManager",
                                                        device_path)

            device_properties = dbus.Interface(device_object,
                                               "org.freedesktop"
                                               ".DBus.Properties").GetAll(
                "org.freedesktop.NetworkManager.Device")
            if device_properties["State"] != 100:
                self.lgr.info(f"Interface {int_name} is not yet activated, "
                              "its routing will be handled when it is")
                return None

            dev_int = dbus.Interface(device_object,
                                     "org.freedesktop.NetworkManager.Device")
            applied = dev_int.GetAppliedConnection(0)
            self.lgr.debug(f"Applied connection is {applied}")
        except dbus.DBusException as e:
            self.lgr.info(f"Failed to retrieve info about {int_name} "
                          "from NetworkManager its routing will be handled when it is ready")
            self.lgr.info(f"{e}")
            return None

        return applied

    def remove_routes(self):
        routes_str = " ".join([str(x) for x in self.routes])
        self.lgr.debug(f"routes: {routes_str}")
        try:
            # we need to refresh the dbus connection, because NetworkManager
            # restart would invalidate it
            self._get_nm_interface()
        except dbus.DBusException:
            self.lgr.info("Failed to contact NetworkManager through dbus, "
                          "will not remove routes")
            return ContextEvent("SUCCESS")

        found_interfaces = {}

        for destination in self.routes:
            found_interfaces[self.routes[destination][1]] = True

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
