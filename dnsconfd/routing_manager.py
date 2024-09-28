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
            self.lgr.debug("Ignored on_device_state_changed call, "
                           "because it had wrong serial")
            return
        if new_state == 100:
            self.interfaces_up[interface] = True
            self.lgr.info("Interface up event on interface %s",
                          interface)
            self.lgr.debug("State was %s reason %s",
                           new_state, reason)
            self.transition_function(ContextEvent("INTERFACE_UP"))
        elif old_state == 100 and new_state != 100:
            self.interfaces_up[interface] = False
            self.lgr.info("Interface down event on interface %s",
                          interface)
            self.lgr.debug("State was %s reason %s",
                           new_state, reason)
            self.transition_function(ContextEvent("INTERFACE_DOWN"))

    def check_ip_object_ready(self, ip_object, interface, family):
        self.lgr.debug("Checking whether ip object %s of interface "
                       "%s is ready, object %s",
                       family, interface, ip_object)
        for route, route_interface in self.routes.values():
            self.lgr.debug("Checking route %s of interface %s",
                           route, route_interface)
            if route_interface != interface:
                self.lgr.debug("This route is not for this interface, "
                               "skipping")
                continue
            parsed_dest = ipaddress.ip_address((route["dest"]))

            if parsed_dest.version != family:
                self.lgr.debug("Wrong family, skipping")
                continue
            route_found = False
            if "RouteData" not in ip_object:
                self.lgr.debug("Object does not contain routes, "
                               "thus not ready")
                return False
            parsed_hop = ipaddress.ip_address(route["next-hop"])
            for obj_route in ip_object["RouteData"]:
                if "next-hop" not in obj_route:
                    continue
                parsed_route_dest = ipaddress.ip_address(obj_route["dest"])
                parsed_route_hop = ipaddress.ip_address(obj_route["next-hop"])
                if (parsed_dest == parsed_route_dest
                        and parsed_route_hop == parsed_hop):
                    route_found = True
                    break
            if not route_found:
                self.lgr.debug("interface %s family %s ip object "
                               "is not ready because it has not route",
                               interface,
                               family)
                self.lgr.debug("%s", route["dest"])
                self.lgr.debug("ip object %s", ip_object)
                self.lgr.debug("routes: %s", self.routes)
                return False
        return True

    def on_ip_obj_change(self, cur_serial: int, interface: int, properties: dict, family: int):
        self.lgr.debug("on_ip_obj_change called %s %s %s",
                       interface, properties, family)
        if self.ip_serial != cur_serial or "RouteData" not in properties:
            self.lgr.debug("Rejected because of bad serial or RouteData")
            return
        ready = self.check_ip_object_ready(properties, interface, family)
        if family == 4:
            old = self.interface_ip_ready[interface][1]
            self.interface_ip_ready[interface] = ready, old
        else:
            old = self.interface_ip_ready[interface][0]
            self.interface_ip_ready[interface] = old, ready
        self.lgr.debug("ready is %s", ready)
        event = ContextEvent("IP_SET") if ready else ContextEvent("IP_UNSET")
        self.transition_function(event)

    def are_all_ip_set(self):
        self.lgr.debug("are_all_ip_set called %s", self.interface_ip_ready)
        for interface, booleans in self.interface_ip_ready.items():
            if not (booleans[0] and booleans[1]):
                return False
        return True

    def _subscribe_ip_family_obj(self, device_properties, family, interface):
        self.lgr.debug("_subscribe_ip_family_obj of %s %s",
                       family, interface)
        nm_dbus_name = "org.freedesktop.NetworkManager"
        conf_key = "Ip4Config" if family == 4 else "Ip6Config"
        config_path = device_properties[conf_key]
        conf_obj = dbus.SystemBus().get_object(nm_dbus_name, config_path)
        serial = self.ip_serial
        intfc = dbus.Interface(conf_obj,
                               "org.freedesktop.DBus.Properties")
        cb = lambda dbus_int, props, invalid: self.on_ip_obj_change(serial,
                                                                    interface,
                                                                    props,
                                                                    family)
        connection = intfc.connect_to_signal("PropertiesChanged",
                                             cb)
        self.lgr.debug("Successfully connected to ip %s of %s",
                       family, interface)
        if family == 4:
            shuffle = (connection, None)
        else:
            shuffle = (self.interface_to_ip_signal_connections[interface][0],
                       connection)
        self.interface_to_ip_signal_connections[interface] = shuffle
        prop_int = dbus.Interface(conf_obj, "org.freedesktop.DBus.Properties")
        if family == 4:
            int_str = "org.freedesktop.NetworkManager.IP4Config"
        else:
            int_str = "org.freedesktop.NetworkManager.IP6Config"
        all_props = prop_int.GetAll(int_str)
        ready = self.check_ip_object_ready(all_props, interface, family)
        self.lgr.debug("ip object ready result %s", ready)
        if family == 4:
            self.interface_ip_ready[interface] = (ready, False)
        else:
            old = self.interface_ip_ready[interface][0]
            self.interface_ip_ready[interface] = (old, ready)

    def _get_device_object_props(self, int_name):
        device_path = self._nm_interface.GetDeviceByIpIface(int_name)
        self.lgr.debug(f"Device path is {device_path}")
        obj = dbus.SystemBus().get_object("org.freedesktop.NetworkManager",
                                          device_path)
        return (obj, dbus.Interface(obj, "org.freedesktop.DBus.Properties")
                .GetAll("org.freedesktop.NetworkManager.Device"))

    def subscribe_to_ip_objs_change(self, interfaces: list[int]):
        if not self._get_nm_interface("subscribe_to_ip_objs_change "
                                      "failed nm connection"):
            return False

        for interface in interfaces:
            int_name = InterfaceConfiguration.get_if_name(interface,
                                                          strict=True)
            if int_name is None:
                self.lgr.debug("Could not get interface name in "
                               "subscribe_to_device_state_change")
                return False
            try:
                dev_obj, dev_props = self._get_device_object_props(int_name)
                self._subscribe_ip_family_obj(dev_props,
                                              4, interface)
                self._subscribe_ip_family_obj(dev_props,
                                              6, interface)
            except dbus.DBusException as e:
                self.lgr.debug("exception encountered during "
                               "subscribe_to_ip_objs_change %s", e)
                return False
        return True

    def subscribe_to_device_state_change(self, interfaces: list[int]):
        if not self._get_nm_interface("Could not connect to nm "
                                      "in subscribe_to_device_state_change"):
            return False
        for interface in interfaces:
            int_name = InterfaceConfiguration.get_if_name(interface, strict=True)
            if int_name is None:
                self.lgr.debug("Could not get interface "
                               "name in subscribe_to_device_state_change")
                return False
            try:
                dev_obj, dev_props = self._get_device_object_props(int_name)
                self.interfaces_up[interface] = dev_props["State"] == 100
                device_interface = (
                    dbus.Interface(dev_obj,
                                   "org.freedesktop.NetworkManager.Device"))
                cur_serial = self.state_serial
                cb = lambda new, old, reason: self.on_device_state_changed(
                    cur_serial,
                    interface,
                    new,
                    old,
                    reason)
                self.interface_to_state_signal_connection[interface] = (
                    device_interface.connect_to_signal("StateChanged", cb))

                self.lgr.debug("Interface %s state %s during subscription",
                               interface,
                               dev_props["State"])
            except dbus.DBusException as e:
                self.lgr.debug("failed subscribe_to_device_state_change %s",
                               e)
                return False
        return True

    def _clear_ip_records(self):
        self.interface_ip_ready = {}
        for interface in self.interface_to_ip_signal_connections:
            self.interface_to_ip_signal_connections[interface][0].remove()
            if self.interface_to_ip_signal_connections[interface][1]:
                self.interface_to_ip_signal_connections[interface][1].remove()

    def clear_subscriptions(self):
        self.change_serials(True, True, True)
        self.interfaces_up = {}
        for interface in self.interface_to_state_signal_connection:
            self.interface_to_state_signal_connection[interface].remove()
        self._clear_ip_records()
        self.interface_to_connection = {}

        for conn in self.dhcp_objs_signal_connections:
            conn.remove()
        self.required_dhcp4 = {}
        self.required_dhcp6 = {}

    def clear_ip_subscriptions(self):
        self.change_serials(False, True, False)
        self._clear_ip_records()

    def check_all_dhcp_ready(self):
        for req_dhcp in [self.required_dhcp4.values(),
                         self.required_dhcp6.values()]:
            for dhcp_dict in req_dhcp:
                if "ip_address" not in dhcp_dict:
                    return False
        return True

    def _on_dhcp_change(self, serial, option_dict, interface, family):
        self.lgr.debug("_on_dhcp_change called, serial %s "
                       "options %s interface %s family %s",
                       serial, option_dict, interface, family)
        if serial != self.dhcp_serial:
            self.lgr.debug("Serial refused")
            return
        if family == 4:
            self.required_dhcp4[interface] = option_dict
        else:
            self.required_dhcp6[interface] = option_dict
        self.transition_function(ContextEvent("DHCP_CHANGE"))

    def _sub_dhcp_obj(self, dev_props, cur_serial, interface, family):
        conf_path = dev_props["Dhcp4Config" if family == 4 else "Dhcp6Config"]
        obj = dbus.SystemBus().get_object("org.freedesktop.NetworkManager",
                                          conf_path)
        dbus_int = dbus.Interface(obj, "org.freedesktop.DBus.Properties")

        cb = lambda interface_str, properties, invalid: self._on_dhcp_change(
            cur_serial,
            properties["Options"],
            interface,
            family)
        connection = dbus_int.connect_to_signal("PropertiesChanged", cb)
        self.dhcp_objs_signal_connections.append(connection)
        self.lgr.debug("Successfully subscribed to interface %s %s object",
                       interface, family)
        dhcp_props = dbus.Interface(obj,
                                    "org.freedesktop"
                                    ".DBus.Properties").GetAll(
            "org.freedesktop.NetworkManager.DHCP4Config")
        self.lgr.debug("Successfully retrieved dhcp properties %s",
                       dhcp_props)
        if family == 4:
            self.required_dhcp4[interface] = dhcp_props["Options"]
        else:
            self.required_dhcp6[interface] = dhcp_props["Options"]

    def subscribe_required_dhcp(self):
        if not self._get_nm_interface("Could not connect to nm "
                                      "in subscribe_required_dhcp"):
            return False

        found_interfaces = []
        for req_array in [self.required_dhcp4, self.required_dhcp6]:
            for i in req_array:
                if i not in found_interfaces:
                    found_interfaces.append(i)

        for if_index in found_interfaces:
            int_name = InterfaceConfiguration.get_if_name(if_index, strict=True)
            if int_name is None:
                self.lgr.debug("Could not get interface name "
                               "in subscribe_required_dhcp")
                return False
            try:
                dev_obj, props = self._get_device_object_props(int_name)
                if if_index in self.required_dhcp4:
                    self.lgr.debug("subscribing to interface %s dhcp4 object"
                                   , if_index)
                    self._sub_dhcp_obj(props, self.dhcp_serial, if_index, 4)
                if if_index in self.required_dhcp6:
                    self.lgr.debug("subscribing to interface %s dhcp6 object"
                                   , if_index)
                    self._sub_dhcp_obj(props, self.dhcp_serial, if_index, 6)
            except dbus.DBusException as e:
                self.lgr.debug("Subscription to dhcp object failed %s", e)
                return False
        return True

    def gather_connections(self, interfaces):
        if not self._get_nm_interface("routing will result when all "
                                      "interfaces are ready"):
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
        if not self._get_nm_interface("routing will result when all "
                                      "interfaces are ready"):
            return False

        interface_to_connection = self.interface_to_connection
        self.lgr.info("Commencing route check")

        found_interfaces = self.interface_to_connection

        self.lgr.debug("interface and connections "
                       f"is {interface_to_connection}")
        interface_names = {}

        for x in found_interfaces:
            interface_names[x] = InterfaceConfiguration.get_if_name(x)

        self.lgr.debug(f"interfaces are {interface_names.values()}")

        interfaces_to_servers = {}
        for server in servers:
            if server.interface is not None:
                interfaces_to_servers.setdefault(server.interface, []).append(
                    server)

        for int_index in found_interfaces:
            valid_routes = {}
            reapply_needed = False
            ifname = interface_names[int_index]

            connection = interface_to_connection[int_index][0]
            self._reset_bin_routes(connection)

            for server in interfaces_to_servers[int_index]:
                server_str = server.get_server_string()
                parsed_server_str = ipaddress.ip_address(server_str)
                connection_existing_route = None
                connection_existing_backup_route = None
                dhcp_existing_route = False
                dhcp_existing_backup_route = False

                self.lgr.info("Checking routing for server %s", server_str)

                same_network = False
                if parsed_server_str.version == 4:
                    ip_dict = connection["ipv4"]
                else:
                    ip_dict = connection["ipv6"]

                dhcp_address_network = None
                dhcp_gateway_str = None
                dhcp_routes = []

                if ip_dict["method"] == "auto":
                    if parsed_server_str.version == 4:
                        dhcp_dict = self.required_dhcp4[int_index]
                    else:
                        dhcp_dict = self.required_dhcp6[int_index]
                    addr_str = dhcp_dict["ip_address"]
                    addr_mask = dhcp_dict["subnet_mask"]
                    if "routers" in dhcp_dict:
                        dhcp_gateway_str = dhcp_dict["routers"].split()[0]
                    if "static_routes" in dhcp_dict:
                        dhcp_routes = dhcp_dict["static_routes"].split()
                    dhcp_address_network = ipaddress.ip_network(
                        f"{addr_str}/{addr_mask}", strict=False)

                for addr in ip_dict["address-data"]:
                    if parsed_server_str in ipaddress.ip_network(
                            f"{addr["address"]}/{addr["prefix"]}",
                            strict=False):
                        same_network = True
                        break
                if (not same_network and dhcp_address_network
                        and parsed_server_str in dhcp_address_network):
                    same_network = True

                if same_network:
                    self.lgr.info("Server %s is in local network, "
                                  "routing not needed", server_str)
                    continue

                for route in ip_dict["route-data"]:
                    route_dest = ipaddress.ip_address(route["dest"])
                    max_prefix = parsed_server_str.max_prefixlen
                    if (route_dest == parsed_server_str
                            and route["prefix"] == max_prefix):
                        connection_existing_route = route
                        break
                for route in ip_dict["route-data"]:
                    route_net = ipaddress.ip_network(
                        f"{route["dest"]}/{route["prefix"]}")
                    if "next-hop" in route and parsed_server_str in route_net:
                        connection_existing_backup_route = route
                        break
                if dhcp_routes and not connection_existing_route:
                    for dest_str, next_hop_str in zip(dhcp_routes[0::2],
                                                      dhcp_routes[1::2]):
                        parsed = ipaddress.ip_network(dest_str, strict=False)
                        net_addr = parsed.network_address
                        if (parsed.prefixlen == parsed.max_prefixlen
                                and net_addr == parsed_server_str):
                            dhcp_existing_route = True
                        elif parsed_server_str in parsed:
                            dhcp_existing_backup_route = ipaddress.ip_address(
                                next_hop_str)

                nexthop_right = False
                next_hop = None
                if connection_existing_route:
                    next_hop = connection_existing_route.get("next-hop", None)

                gateway_in_connection = "gateway" in ip_dict
                if next_hop:
                    parsed_hop = ipaddress.ip_address(next_hop)
                    if (gateway_in_connection
                            and parsed_hop == ipaddress.ip_address(
                                ip_dict["gateway"])):
                        nexthop_right = True
                    elif (dhcp_gateway_str
                          and parsed_hop == ipaddress.ip_address(
                                dhcp_gateway_str)):
                        nexthop_right = True
                if connection_existing_route and nexthop_right:
                    if server_str in self.routes:
                        # route was submitted by us and it is valid
                        valid_routes[server_str] = (connection_existing_route,
                                                    int_index)
                    self.lgr.debug("Routing is right, no additional action "
                                   "required continuing")
                    continue
                elif connection_existing_route:
                    parsed_existing_hop = ipaddress.ip_address(
                        connection_existing_route["next-hop"])
                    if server_str in self.routes:
                        if (not (gateway_in_connection or dhcp_gateway_str)
                                and connection_existing_backup_route):
                            parsed_backup_hop = ipaddress.ip_address(
                                connection_existing_backup_route["next-hop"])
                            if parsed_existing_hop != parsed_backup_hop:
                                self.lgr.info(
                                    "Route exists but the nexthop is not "
                                    "right, to the original broader route "
                                    "from connection, will change it")
                                connection_existing_route["next-hop"] = (
                                    connection_existing_backup_route
                                )["next-hop"]
                            else:
                                self.lgr.info(
                                    "Route exists and it is correct "
                                    "according to broader route from "
                                    "connection")
                                continue
                        elif (not (gateway_in_connection or dhcp_gateway_str)
                              and dhcp_existing_backup_route):
                            if (parsed_existing_hop !=
                                    dhcp_existing_backup_route):
                                self.lgr.info(
                                    "Route exists but the nexthop is not "
                                    "right, to the original broader route "
                                    "from DHCP, will change it")
                                dstr = dbus.String(
                                    str(dhcp_existing_backup_route))
                                connection_existing_route["next-hop"] = dstr
                            else:
                                self.lgr.info("Route exists and it is "
                                              "correct according to broader "
                                              "route from DHCP")
                                continue
                        elif gateway_in_connection or dhcp_gateway_str:
                            self.lgr.info("Route exists but the nexthop "
                                          "is not right, will change it")
                            if gateway_in_connection:
                                new_gw = ip_dict["gateway"]
                            else:
                                new_gw = dbus.String(dhcp_gateway_str)
                            connection_existing_route["next-hop"] = new_gw
                        else:
                            self.lgr.error(
                                "Route exists but the nexthop is not right "
                                "and default gateway is not set, waiting "
                                "for it to be set or until route occurs")
                            return False
                    else:
                        self.lgr.warning(
                            "Route exists but the nexthop is not right and "
                            "it was not submitted by us, relying on your "
                            "network configuration")
                        continue

                    valid_routes[server_str] = (connection_existing_route,
                                                int_index)
                    reapply_needed = True
                elif dhcp_existing_route:
                    self.lgr.warning(
                        "Route exists, but it was received through DHCP, "
                        "relying on your network configuration")
                    continue
                else:
                    if gateway_in_connection or dhcp_gateway_str:
                        self.lgr.debug("Route does not exist, creating it")
                        if gateway_in_connection:
                            gateway_dbus_string = ip_dict["gateway"]
                        else:
                            gateway_dbus_string = dbus.String(
                                dhcp_gateway_str)
                    elif connection_existing_backup_route:
                        self.lgr.info(
                            "Route does not exist, however there is route "
                            "in connection that would contain this server, "
                            "will create its specified version")
                        nhop = connection_existing_backup_route["next-hop"]
                        gateway_dbus_string = nhop
                    elif dhcp_existing_backup_route:
                        self.lgr.info(
                            "Route does not exist, however there is route "
                            "gotten through DHCP that would contain this "
                            "server, will create its specified version")
                        gateway_dbus_string = dbus.String(
                            str(dhcp_existing_backup_route))
                    else:
                        self.lgr.error("Route does not exist, and gateway "
                                       "is not set, waiting until it is")
                        return False

                    new_route = dbus.Dictionary({
                        dbus.String("dest"):
                            dbus.String(server_str),
                        dbus.String("prefix"):
                            dbus.UInt32(parsed_server_str.max_prefixlen),
                        dbus.String("next-hop"):
                            gateway_dbus_string})
                    self.lgr.info("New route is: %s and will be "
                                  "submitted for interface %s"
                                  , new_route, int_index)
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
                    self.lgr.warning("Failed to reapply connection to "
                                     "%s, %s will wait", ifname, e)
                    return False
                for destination in list(self.routes):
                    if self.routes[destination][1] == int_index:
                        self.routes.pop(destination)
                self.routes.update(valid_routes)

        # now if there are routes in self.routes for interfaces that are
        # not in found_interfaces, that means that there are either
        # bogus routes or those interfaces were downed thus
        # walk them, remove bogus routes and then delete them from
        # self.routes
        downed_interfaces = []
        for route, interface in list(self.routes.values()):
            if (interface not in found_interfaces
                    and interface not in downed_interfaces):
                downed_interfaces.append(interface)
                int_name = InterfaceConfiguration.get_if_name(interface,
                                                              strict=True)
                if int_name is not None:
                    self.lgr.debug("Will remove old routes from "
                                   "interface %s", int_name)
                    try:
                        dev_obj, dev_props = self._get_device_object_props(
                            int_name)
                        if dev_props["State"] == 100:
                            ip4_rte, ip6_rte, applied = (
                                self._get_nm_device_config(interface))
                            if self._remove_checked_routes(applied[0], None):
                                self._reapply_routes(int_name,
                                                     applied[0],
                                                     applied[1])
                    except dbus.DBusException:
                        # this is just a debug message, bec
                        self.lgr.info("Failed to clean interface %s "
                                      "will try again",
                                      int_name)
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
                dest_str = str(checked_route["dest"])
                if (dest_str in self.routes
                        and (valid_routes is None
                             or dest_str not in valid_routes)):
                    connection[family]["route-data"].remove(checked_route)
                    modified = True
                    self.lgr.info(f"Removing %s route %s",
                                  family, checked_route)
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

    def _get_nm_interface(self, fail_message):
        try:
            nm_dbus_name = "org.freedesktop.NetworkManager"
            nm_dbus_obj_path = '/org/freedesktop/NetworkManager'
            nm_object = dbus.SystemBus().get_object(nm_dbus_name,
                                                    nm_dbus_obj_path)
            self._nm_interface = dbus.Interface(nm_object,
                                                nm_dbus_name)
        except dbus.DBusException as e:
            self.lgr.debug("Could not connect to NM %s", e)
            self.lgr.info(fail_message)
            return None
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
            self.lgr.info("interface %s has no name and thus "
                          "we will not handle its routing now", index)
            return None
        self.lgr.debug(f"Getting NetworkManager info about %s", int_name)
        try:
            dev_obj, dev_props = self._get_device_object_props(int_name)
            dev_int = dbus.Interface(dev_obj,
                                     "org.freedesktop.NetworkManager.Device")
            applied = dev_int.GetAppliedConnection(0)
            self.lgr.debug(f"Applied connection is %s", applied)
        except dbus.DBusException as e:
            self.lgr.info("Failed to retrieve info about %s "
                          "from NetworkManager its routing will be "
                          "handled when it is ready", int_name)
            self.lgr.debug("exception: %s", e)
            return None
        return applied

    def remove_routes(self):
        routes_str = " ".join([str(x) for x in self.routes])
        self.lgr.debug(f"routes: {routes_str}")
        if not self._get_nm_interface("Failed to contact NetworkManager "
                                      "through dbus, will not remove routes"):
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
                              "%s, Will not remove its routes", ifname)
                continue

            if self._remove_checked_routes(connection, None):
                reapply_needed = True

            if reapply_needed:
                try:
                    self._reapply_routes(ifname, connection, cver)
                except dbus.DBusException as e:
                    self.lgr.warning("Failed to reapply connection of "
                                     "%s, Will not remove its routes. "
                                     "%s", ifname, e)
                    continue
        return ContextEvent("SUCCESS")
