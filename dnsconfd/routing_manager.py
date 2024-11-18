import functools
import ipaddress
import logging
from copy import deepcopy
from typing import Any, Callable
import dbus

from dnsconfd.fsm import ContextEvent
from dnsconfd.network_objects import ServerDescription


class RoutingManager:
    def __init__(self, transition_function: Callable):
        """ Object responsible for managing of routes

        This code was created in a way that always leaves this object
        in consistent state after calling of public methods, so
        the caller does not have to keep track of any information.

        :param transition_function: function that should be called when
        transition is necessary
        """
        self._nm_interface = None
        self.lgr = logging.getLogger(self.__class__.__name__)

        # routes submitted to host
        self.routes = {}

        # servers that were present at the start of the transaction
        self.current_transaction_servers = []

        # watching connections' state
        self.interface_to_state_signal_connection = {}
        self.interfaces_up = {}

        # watching true device state
        self.interface_ip_objects = {}
        self.interface_to_ip_signal_connections = []

        # these allow us to ignore old events
        self.serial = 0

        self.transition_function = transition_function

        # already gathered connection information of interfaces
        self.interface_to_connection = {}

    def are_all_up(self) -> bool:
        """ Check whether all required interfaces are activated

        :return: True if required interfaces are activated, otherwise False
        """
        for is_up in self.interfaces_up.values():
            if not is_up:
                return False
        return True

    def _on_device_state_changed(self, new_state, old_state,
                                 reason, serial=0, interface=0):
        # it is possible, that dbus event was already dispatched
        # that belonged to previous update, and we need to ensure
        # this will be ignored, since we can not remove them
        if self.serial != serial:
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

    def _check_ip_object_contains_routes(self, ip_object, interface, family):
        self.lgr.debug("_check_ip_object_contains_routes ip_object %s, "
                       "interface %s, family %s",
                       ip_object, interface, family)
        for srv_str, (route, route_interface) in list(self.routes.items()):
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
            ip_key = "ipv4" if family == 4 else "ipv6"
            conn_dict = self.interface_to_connection[interface][0][ip_key]
            conn_route_present = False
            for conn_route in conn_dict["route-data"]:
                if conn_route["prefix"] != parsed_dest.max_prefixlen:
                    continue
                parsed_conn_rt_dest = ipaddress.ip_address(conn_route["dest"])
                if parsed_dest == parsed_conn_rt_dest:
                    conn_route_present = True
                    break
            if not conn_route_present:
                self.lgr.debug("We were about to check presence of "
                               "route %s in ip_object of interface %s but "
                               "it is no longer in connection",
                               route, interface)
                self.routes.pop(srv_str)
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

    def _check_ip_object_ready(self, ip_object, interface, family):
        self.lgr.debug("Checking whether ip object %s of interface "
                       "%s is ready, object %s",
                       family, interface, ip_object)
        # we need to check that for each known server bound
        # to this interface there is either:
        # 1. Gateway
        # 2. Already existing precise route for it
        # 3. Route that would contain this server and we just need
        #    to create its more specific copy
        try:
            ipaddress.ip_address(ip_object.get("Gateway", ""))
            # gateway is there, that is the minimum we need
            self.lgr.debug("IP object has gateway, thus ready")
            return True
        except ValueError:
            pass
        # now there has to be either specific route or at least backup route

        this_object_servers = [a for a in self.current_transaction_servers
                               if a.interface == interface
                               and a.is_family(family)]
        if "AddressData" in ip_object:
            for srv in list(this_object_servers):
                parsed_srv = ipaddress.ip_address(srv.address)
                for address in ip_object["AddressData"]:
                    parsed_net = ipaddress.ip_network(
                        f"{address["address"]}/{address["prefix"]}",
                        strict=False)
                    if parsed_srv in parsed_net:
                        self.lgr.debug("server %s is in interface local "
                                       "network", parsed_srv)
                        this_object_servers.remove(srv)
        if not this_object_servers:
            return True

        if "RouteData" in ip_object:
            for srv in this_object_servers:
                parsed_srv = ipaddress.ip_address(srv.address)
                found = False
                for route_obj in ip_object["RouteData"]:
                    if "dest" not in route_obj or "prefix" not in route_obj:
                        continue
                    if parsed_srv in ipaddress.ip_network(
                            f"{route_obj["dest"]}/{route_obj["prefix"]}",
                            strict=False):
                        found = True
                        break
                if not found:
                    self.lgr.debug("IP object is not ready to route %s",
                                   parsed_srv)
                    return False
            return True

        self.lgr.debug("IP object has no gateway and routes, thus is not "
                       "ready for routing")
        return False

    def _on_ip_obj_change(self, cur_serial: int, interface: int,
                          properties: dict, family: int):
        self.lgr.debug("on_ip_obj_change called %s %s %s",
                       interface, properties, family)
        if self.serial != cur_serial:
            self.lgr.debug("Rejected because of bad serial")
            return
        whole_object = self.interface_ip_objects[interface][family]
        whole_object.update(properties)
        ready = self._check_ip_object_ready(whole_object, interface, family)
        self.lgr.debug("ready is %s", ready)
        if ready:
            event = ContextEvent("IP_READY")
        else:
            event = ContextEvent("IP_NOT_READY")
        self.transition_function(event)

    def is_any_ip_object_ready(self):
        """ Check whether there is at least one ip object that we
            can use for routing
        """
        self.lgr.debug("is_any_ip_object_ready called %s",
                       self.interface_ip_objects)
        if not self.interface_ip_objects:
            return True

        routing_possible = False

        # all ip objects must have routes that we submitted, but
        # it is sufficient if just one has routing ready
        for interface, ip_objects in self.interface_ip_objects.items():
            for family in [4, 6]:
                if ip_objects.get(family, None) is not None:
                    if not self._check_ip_object_contains_routes(
                            ip_objects[family], interface, family):
                        return False
                    if (not routing_possible
                            and self._check_ip_object_ready(
                                ip_objects[family], interface, family)):
                        routing_possible = True

        return routing_possible

    def _subscribe_ip_family_obj(self, device_properties, family, interface):
        self.lgr.debug("_subscribe_ip_family_obj family %s interface %s",
                       family, interface)
        nm_dbus_name = "org.freedesktop.NetworkManager"
        conf_key = "Ip4Config" if family == 4 else "Ip6Config"
        config_path = device_properties[conf_key]
        if str(config_path) == "/":
            return
        self.lgr.debug("_subscribe_ip_family_obj object path %s", config_path)
        conf_obj = dbus.SystemBus().get_object(nm_dbus_name, config_path)
        serial = self.serial
        intfc = dbus.Interface(conf_obj,
                               "org.freedesktop.DBus.Properties")
        cb = lambda dbus_int, props, invalid: self._on_ip_obj_change(serial,
                                                                     interface,
                                                                     props,
                                                                     family)
        connection = intfc.connect_to_signal("PropertiesChanged",
                                             cb)
        self.lgr.debug("Successfully connected to ip %s of %s",
                       family, interface)
        self.interface_to_ip_signal_connections.append(connection)
        prop_int = dbus.Interface(conf_obj, "org.freedesktop.DBus.Properties")
        if family == 4:
            int_str = "org.freedesktop.NetworkManager.IP4Config"
        else:
            int_str = "org.freedesktop.NetworkManager.IP6Config"
        all_props = prop_int.GetAll(int_str)
        self.lgr.debug("ip object props %s", all_props)
        self.interface_ip_objects.setdefault(interface, {})[family] = (
            all_props)

    def _get_device_object_props(self, int_name):
        device_path = self._nm_interface.GetDeviceByIpIface(int_name)
        self.lgr.debug("Device path is %s", device_path)
        obj = dbus.SystemBus().get_object("org.freedesktop.NetworkManager",
                                          device_path)
        return (obj, dbus.Interface(obj, "org.freedesktop.DBus.Properties")
                .GetAll("org.freedesktop.NetworkManager.Device"))

    def subscribe_to_ip_objs_change(self):
        """ Subscribe to interfaces ip objects

        :return: True if all was successful, otherwise False
        """
        if not self._get_nm_interface("subscribe_to_ip_objs_change "
                                      "failed nm connection"):
            return False

        needed = {}
        for srv in self.current_transaction_servers:
            if srv.interface is not None:
                fam = 4 if srv.is_family(4) else 6
                needed.setdefault(srv.interface, {})[fam] = True

        for int_name, need_dict in needed.items():
            try:
                dev_obj, dev_props = self._get_device_object_props(int_name)
                if need_dict.get(4, False):
                    self._subscribe_ip_family_obj(dev_props,
                                                  4, int_name)
                if need_dict.get(6, False):
                    self._subscribe_ip_family_obj(dev_props,
                                                  6, int_name)
            except dbus.DBusException as e:
                self.lgr.debug("exception encountered during "
                               "subscribe_to_ip_objs_change %s", e)
                return False
        return True

    def subscribe_to_device_state_change(
            self, servers: list[ServerDescription]) -> bool:
        """ Subscribe to state changes of interfaces that servers are bound to
            This is also beginning of routing transaction and before next
            call, clear_transaction should be called
        :param servers: servers whose routing will be handled
        :return: True on Success otherwise, False
        """
        if not self._get_nm_interface("Could not connect to nm "
                                      "in subscribe_to_device_state_change"):
            return False
        interfaces = {}
        for server in servers:
            if server.interface is None:
                continue
            interfaces[server.interface] = True

        for interface in interfaces:
            try:
                dev_obj, dev_props = self._get_device_object_props(interface)
                self.interfaces_up[interface] = dev_props["State"] == 100
                device_interface = (
                    dbus.Interface(dev_obj,
                                   "org.freedesktop.NetworkManager.Device"))
                cb = functools.partial(self._on_device_state_changed,
                                       serial=self.serial,
                                       interface=interface)
                self.interface_to_state_signal_connection[interface] = (
                    device_interface.connect_to_signal("StateChanged", cb))

                self.lgr.debug("Interface %s state %s during subscription",
                               interface,
                               dev_props["State"])
            except dbus.DBusException as e:
                self.lgr.debug("failed subscribe_to_device_state_change %s",
                               e)
                return False

        self.current_transaction_servers = deepcopy(servers)
        return True

    def clear_transaction(self):
        """ Clear all subscriptions and state data """
        self.serial = self.serial + 1 if self.serial < 1000 else 0
        self.interfaces_up = {}
        for interface in self.interface_to_state_signal_connection:
            self.interface_to_state_signal_connection[interface].remove()
        self.interface_to_state_signal_connection = {}
        self.interface_ip_objects = {}
        for conn in self.interface_to_ip_signal_connections:
            conn.remove()
        self.interface_to_ip_signal_connections = []
        self.interface_to_connection = {}
        self.current_transaction_servers = []

    def gather_connections(self):
        """ Gather connections of interfaces that we are interested in

        :return: True on success, otherwise False
        """
        if not self._get_nm_interface("routing will result when all "
                                      "interfaces are ready"):
            return False

        for if_index in self.interfaces_up:
            applied = self._get_nm_device_config(if_index)
            if applied is None:
                self.lgr.debug("All interfaces were not "
                               "ready to gather connections")
                return False
            self.interface_to_connection[if_index] = applied

        return True

    def handle_routes_process(self) -> tuple[list[ServerDescription], int]:
        """ Check routing and attempt to create appropriate routes

        Routing Algorithm works like this:
        1. If server's address is in local network, no routing is needed
        2. If interface has gateway set then we create route to gateway
        3. If there is more broad route that would be used, then we create
           its more specific version
        4. otherwise server will not be allowed

        :return: list of routed servers and 0 when no route was submitted
                 1 when route/s were submitted and 2 on error
        """
        # we need to refresh the dbus connection, because NetworkManager
        # restart would invalidate it
        routed_servers = []
        if not self._get_nm_interface("routing will result when all "
                                      "interfaces are ready"):
            return [], 2
        rc = 0
        interface_to_connection = self.interface_to_connection
        self.lgr.info("Commencing route check")

        found_interfaces = self.interface_to_connection

        self.lgr.debug("interface and connections %s",
                       interface_to_connection)

        interfaces_to_servers = {}
        for server in self.current_transaction_servers:
            if server.interface is not None:
                interfaces_to_servers.setdefault(server.interface, []).append(
                    server)
            else:
                routed_servers.append(server)

        for int_index in found_interfaces:
            valid_routes = {}
            reapply_needed = False
            ifname = int_index

            connection = interface_to_connection[int_index][0]
            self._reset_bin_routes(connection)

            if int_index not in self.interface_ip_objects:
                self.lgr.debug("There is no IP object for "
                               "interface %s continuing", int_index)
                continue
            temp_routed_servers = []
            for server in interfaces_to_servers[int_index]:
                server_str = server.get_server_string()
                parsed_server_str = ipaddress.ip_address(server_str)

                self.lgr.info("Checking routing for server %s", server_str)

                family = parsed_server_str.version
                ip_dict = self.interface_ip_objects[int_index].get(family,
                                                                   None)
                if ip_dict is None:
                    self.lgr.debug("There is no ip data for family %s of "
                                   "interface %s, continuing",
                                   family, ifname)
                    continue
                if "RouteData" not in ip_dict:
                    self.lgr.debug("There is no route data in ip_dict "
                                   "%s, continuing", ip_dict)

                present_gateway = None
                parsed_present_gateway = None
                try:
                    parsed_present_gateway = ipaddress.ip_address(
                        ip_dict["Gateway"])
                    present_gateway = ip_dict["Gateway"]
                except ValueError:
                    pass

                present_specific_route = None
                present_backup_route = None
                for route_obj in ip_dict["RouteData"]:
                    max_prefix = parsed_server_str.max_prefixlen
                    if parsed_server_str not in ipaddress.ip_network(
                            f"{route_obj["dest"]}/{route_obj["prefix"]}",
                            strict=False):
                        continue
                    if route_obj["prefix"] == max_prefix:
                        present_specific_route = route_obj
                    elif "next-hop" not in route_obj:
                        continue
                    elif present_backup_route is None:
                        present_backup_route = route_obj
                    elif present_backup_route["prefix"] < route_obj["prefix"]:
                        present_backup_route = route_obj
                    elif present_backup_route["metric"] > route_obj["metric"]:
                        present_backup_route = route_obj

                nexthop_right = False
                if (present_specific_route
                        and "next-hop" in present_specific_route):
                    if parsed_present_gateway:
                        parsed_hop = ipaddress.ip_address(
                                        present_specific_route["next-hop"])
                        nexthop_right = parsed_present_gateway == parsed_hop
                    elif present_backup_route:
                        sp_rt_hop = ipaddress.ip_address(
                            present_specific_route["next-hop"])
                        bk_rt_hop = ipaddress.ip_address(
                            present_backup_route["next-hop"])
                        nexthop_right = sp_rt_hop == bk_rt_hop

                same_network = False
                if "AddressData" in ip_dict and ip_dict["AddressData"]:
                    for address in ip_dict["AddressData"]:
                        net = ipaddress.ip_network(
                            f"{address["address"]}/{address["prefix"]}",
                            strict=False)
                        if parsed_server_str in net:
                            same_network = True
                            break
                if same_network:
                    self.lgr.info("Server is in the same network as "
                                  "interface, routing not needed")
                    self.lgr.debug("Appending %s to routed servers", server)
                    routed_servers.append(server)
                    continue
                elif present_specific_route and nexthop_right:
                    # correct route is present
                    if server_str in self.routes:
                        # route was submitted by us and it is valid
                        valid_routes[server_str] = (present_specific_route,
                                                    int_index)
                    self.lgr.info("Routing is right, no additional action "
                                  "required continuing")
                    self.lgr.debug("Appending %s to routed servers", server)
                    routed_servers.append(server)
                    continue
                elif present_specific_route:
                    # route is there, but the dest is not correct
                    # the next hop check here is more of a paranoia
                    if ("next-hop" not in present_specific_route
                            or server_str not in self.routes):
                        self.lgr.info("The route does not have correct"
                                      "destination according to gateway or "
                                      "broader route, but it was not "
                                      "submitted by us, thus relying on your "
                                      "network configuration")
                        self.lgr.debug("Appending %s to routed servers",
                                       server)
                        routed_servers.append(server)
                        continue
                    # route was submitted by us, change dest to gateway or
                    # dest of broader route
                    if present_gateway:
                        new_hop_dbus_string = present_gateway
                    elif present_backup_route:
                        new_hop_dbus_string = present_backup_route["next-hop"]
                    else:
                        self.lgr.debug("The route was submitted by us, "
                                       "but we have no way of determining "
                                       "correct destination, thus waiting")
                        continue
                    found_route = None
                    fam_data = connection["ipv4" if family == 4 else "ipv6"]
                    for con_route in fam_data["route-data"]:
                        parsed_route_dest = ipaddress.ip_address(
                            con_route["dest"])
                        if parsed_route_dest == parsed_server_str:
                            found_route = con_route
                            break
                    found_route["next-hop"] = new_hop_dbus_string
                    valid_routes[server_str] = (found_route, int_index)
                    self.lgr.info("New destination will be %s",
                                  new_hop_dbus_string)
                    reapply_needed = True
                    self.lgr.debug("Appending %s to temp routed servers",
                                   server)
                    temp_routed_servers.append(server)
                    continue
                else:
                    # no specific route exists, try to create one
                    if present_gateway:
                        new_hop_dbus_string = present_gateway
                    elif present_backup_route:
                        new_hop_dbus_string = present_backup_route["next-hop"]
                    else:
                        self.lgr.info("Unable to determine route "
                                      "destination, will wait")
                        continue
                    new_route = dbus.Dictionary({
                        dbus.String("dest"):
                            dbus.String(server_str),
                        dbus.String("prefix"):
                            dbus.UInt32(parsed_server_str.max_prefixlen),
                        dbus.String("next-hop"):
                            new_hop_dbus_string})
                    valid_routes[server_str] = (new_route, int_index)
                    fam_data = connection["ipv4" if family == 4 else "ipv6"]
                    fam_data["route-data"].append(new_route)
                    reapply_needed = True
                    self.lgr.debug("Appending %s to temp routed servers",
                                   server)
                    temp_routed_servers.append(server)
            if self._remove_checked_routes(connection, valid_routes):
                reapply_needed = True
                rc = 1
            if reapply_needed:
                try:
                    cver = interface_to_connection[int_index][1]
                    self._reapply_routes(ifname, connection, cver)
                except dbus.DBusException as e:
                    self.lgr.warning("Failed to reapply connection to "
                                     "%s, %s will wait", ifname, e)
                    return [], 2
                rc = 1
                for destination in list(self.routes):
                    if self.routes[destination][1] == int_index:
                        self.routes.pop(destination)
                self.routes.update(valid_routes)
                self.lgr.debug("Extending routed servers with %s",
                               temp_routed_servers)
                routed_servers.extend(temp_routed_servers)
        self.lgr.debug("Routed servers %s", routed_servers)
        return routed_servers, rc

    def remove_redundant(self):
        """ Remove routes from interfaces that no longer interest us

        :return: True on success otherwise False
        """
        # interface_to_connection, that means that there are either
        # bogus routes or those interfaces were downed thus
        # walk them, remove bogus routes and then delete them from
        # self.routes
        if not self._get_nm_interface("Failed to contact NetworkManager "
                                      "through dbus, will attempt to remove"
                                      "redundant routes later"):
            return False
        downed_interfaces = []
        for route, int_name in list(self.routes.values()):
            if (int_name not in self.interface_to_connection
                    and int_name not in downed_interfaces):
                downed_interfaces.append(int_name)
                self.lgr.debug("Will remove old routes from "
                               "interface %s", int_name)
                try:
                    dev_obj, dev_props = self._get_device_object_props(
                        int_name)
                    if dev_props["State"] == 100:
                        applied = self._get_nm_device_config(int_name)
                        if self._remove_checked_routes(applied[0], None):
                            self._reapply_routes(int_name,
                                                 applied[0],
                                                 applied[1])
                except dbus.DBusException as e:
                    # this happens when interface is removed from the system
                    self.lgr.info("Failed to clean interface %s "
                                  ", %s, considering it cleaned",
                                  e, int_name)
                for destination in list(self.routes):
                    if self.routes[destination][1] == int_name:
                        self.routes.pop(destination)
        return True

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
                    self.lgr.info("Removing %s route %s",
                                  family, checked_route)
        return modified

    def _get_nm_device_interface(self, ifname):
        """Get DBus proxy object of Device identified by ifname."""
        device_path = self._nm_interface.GetDeviceByIpIface(ifname)
        self.lgr.debug("Device path is %s", device_path)
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
        self.lgr.info("New ipv4 route data %s",
                      connection["ipv4"]["route-data"])
        self.lgr.info("New ipv6 route data %s",
                      connection["ipv6"]["route-data"])
        dev_int = self._get_nm_device_interface(ifname)
        dev_int.Reapply(connection, cver, 0)

    @staticmethod
    def _reset_bin_routes(connection):
        # we need to remove this, so we can use route-data field
        # undocumented NetworkManager implementation detail
        connection["ipv4"].pop("routes", None)
        connection["ipv6"].pop("routes", None)

    def _get_nm_device_config(self, int_name):
        self.lgr.debug("Getting NetworkManager info about %s", int_name)
        try:
            dev_obj, dev_props = self._get_device_object_props(int_name)
            dev_int = dbus.Interface(dev_obj,
                                     "org.freedesktop.NetworkManager.Device")
            applied = dev_int.GetAppliedConnection(0)
            self.lgr.debug("Applied connection is %s", applied)
        except dbus.DBusException as e:
            self.lgr.info("Failed to retrieve info about %s "
                          "from NetworkManager its routing will be "
                          "handled when it is ready", int_name)
            self.lgr.debug("exception: %s", e)
            return None
        return applied

    def remove_routes(self):
        """ Try to remove all routes that were submitted by Dnsconfd """
        routes_str = " ".join([str(x) for x in self.routes])
        self.lgr.debug("routes: %s", routes_str)
        if not self._get_nm_interface("Failed to contact NetworkManager "
                                      "through dbus, will not remove routes"):
            return

        found_interfaces = {}

        for destination in self.routes.values():
            found_interfaces[destination[1]] = True

        for ifname in found_interfaces:
            reapply_needed = False
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
