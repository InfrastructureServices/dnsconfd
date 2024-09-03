from dnsconfd.network_objects import InterfaceConfiguration, ServerDescription
from dnsconfd.dns_managers import UnboundManager
from dnsconfd.fsm import ContextEvent
from dnsconfd.fsm import ContextState
from dnsconfd import SystemManager
from dnsconfd.fsm import ExitCode

from gi.repository import GLib
from typing import Callable
import logging
import dbus
import json
import ipaddress


class DnsconfdContext:
    def __init__(self, config: dict, main_loop: object):
        """ Class containing implementation of FSM that controls Dnsconfd
        operations

        :param config: dict containing network_objects
        :type config: dict
        :param main_loop: Main loop provided by GLib
        :type main_loop: object
        """
        self.lgr = logging.getLogger(self.__class__.__name__)

        self.my_address = config["listen_address"]

        self.dnssec_enabled = config["dnssec_enabled"]
        self.wire_priority = config["prioritize_wire"]
        self.handle_routes = config["handle_routing"]

        self.global_resolvers = {}

        for zone, resolvers in config["static_servers"].items():
            self.global_resolvers[zone] = []
            for resolver in resolvers:
                prot = resolver.get("protocol", "plain")
                port = resolver.get("port", None)
                sni = resolver.get("sni", None)
                new_srv = ServerDescription.from_config(resolver["address"],
                                                        prot,
                                                        port,
                                                        sni)
                self.global_resolvers[zone].append(new_srv)

        self.sys_mgr = SystemManager(config)
        self._main_loop = main_loop

        self._systemd_manager = None
        self._nm_interface = None
        self._signal_connection = None

        self.dns_mgr = None
        self.interfaces: dict[int, InterfaceConfiguration] = {}

        self.routes = {}

        # dictionary, systemd jobs -> event that should be emitted on success,
        # event that should be emitted on failure
        self._systemd_jobs: dict[int, tuple[ContextEvent, ContextEvent]] = {}
        self._exit_code = 0
        self.state = ContextState.STARTING
        self.transition: dict[
            ContextState,
            dict[str,
                 tuple[ContextState,
                       Callable[[DnsconfdContext, ContextEvent],
                                ContextEvent]]]] = {
            ContextState.STARTING: {
                "KICKOFF": (ContextState.CONFIGURING_DNS_MANAGER,
                            self._starting_kickoff_transition),
                "UPDATE": (ContextState.STARTING,
                           self._update_transition),
                "STOP": (ContextState.STOPPING,
                         self._exit_transition)
            },
            ContextState.CONFIGURING_DNS_MANAGER: {
                "SUCCESS": (ContextState.CONNECTING_DBUS,
                            self._conf_dns_mgr_success_transition),
                "FAIL": (ContextState.STOPPING,
                         self._exit_transition)
            },
            ContextState.CONNECTING_DBUS: {
                "FAIL": (ContextState.STOPPING,
                         self._exit_transition),
                "SUCCESS": (ContextState.SUBMITTING_START_JOB,
                            self._connecting_dbus_success_transition)
            },
            ContextState.SUBMITTING_START_JOB: {
                "FAIL": (ContextState.STOPPING,
                         self._exit_transition),
                "SUCCESS": (ContextState.WAITING_FOR_START_JOB,
                            lambda y: None)
            },
            ContextState.STOPPING: {
                "EXIT": (ContextState.STOPPING,
                         self._exit_transition)
            },
            ContextState.WAITING_FOR_START_JOB: {
                "START_OK": (ContextState.POLLING,
                             self._job_finished_success_transition),
                "START_FAIL": (ContextState.STOPPING,
                               self._service_failure_exit_transition),
                "UPDATE": (ContextState.WAITING_FOR_START_JOB,
                           self._update_transition),
                "STOP": (ContextState.WAITING_TO_SUBMIT_STOP_JOB,
                         lambda y: None)
            },
            ContextState.WAITING_TO_SUBMIT_STOP_JOB: {
                "START_OK": (ContextState.SUBMITTING_STOP_JOB,
                             self._waiting_to_submit_success_transition),
                "START_FAIL": (ContextState.REMOVING_ROUTES,
                               self._to_removing_routes_transition),
                "STOP": (ContextState.WAITING_TO_SUBMIT_STOP_JOB,
                         lambda y: None),
                "UPDATE": (ContextState.WAITING_TO_SUBMIT_STOP_JOB,
                           lambda y: None),
                "RESTART_SUCCESS": (ContextState.REVERTING_RESOLV_CONF,
                                    self._running_stop_transition),
                "RESTART_FAIL": (ContextState.REVERTING_RESOLV_CONF,
                                 self._restart_failure_stop_transition)
            },
            ContextState.POLLING: {
                "TIMER_UP": (ContextState.POLLING,
                             self._polling_timer_up_transition),
                "SERVICE_UP": (ContextState.SETTING_UP_RESOLVCONF,
                               self._polling_service_up_transition),
                "TIMEOUT": (ContextState.STOPPING,
                            self._exit_transition),
                "UPDATE": (ContextState.POLLING,
                           self._update_transition),
                "STOP": (ContextState.REVERTING_RESOLV_CONF,
                         self._running_stop_transition)
            },
            ContextState.SETTING_UP_RESOLVCONF: {
                "FAIL": (ContextState.STOPPING,
                         self._exit_transition),
                "SUCCESS": (ContextState.UPDATING_RESOLV_CONF,
                            self._setting_up_resolve_conf_transition)
            },
            ContextState.RUNNING: {
                "UPDATE": (ContextState.UPDATING_RESOLV_CONF,
                           self._running_update_transition),
                "STOP": (ContextState.REVERTING_RESOLV_CONF,
                         self._running_stop_transition),
                "RELOAD": (ContextState.SUBMITTING_RESTART_JOB,
                           self._running_reload_transition)
            },
            ContextState.UPDATING_RESOLV_CONF: {
                "FAIL": (ContextState.SUBMITTING_STOP_JOB,
                         self._updating_resolv_conf_fail_transition),
                "SUCCESS": (ContextState.UPDATING_ROUTES,
                            self._updating_resolv_conf_success_transition)
            },
            ContextState.UPDATING_ROUTES: {
                "FAIL": (ContextState.REVERTING_RESOLV_CONF,
                         self._running_stop_transition),
                "SUCCESS": (ContextState.UPDATING_DNS_MANAGER,
                            self._updating_routes_success_transition)
            },
            ContextState.UPDATING_DNS_MANAGER: {
                "FAIL": (ContextState.REVERTING_RESOLV_CONF,
                         self.updating_dns_manager_fail_transition),
                "SUCCESS": (ContextState.RUNNING, lambda y: None)
            },
            ContextState.SUBMITTING_STOP_JOB: {
                "SUCCESS": (ContextState.WAITING_STOP_JOB, lambda y: None),
                "FAIL": (ContextState.REMOVING_ROUTES,
                         self._to_removing_routes_transition)
            },
            ContextState.WAITING_STOP_JOB: {
                "STOP_SUCCESS": (ContextState.REMOVING_ROUTES,
                                 self._to_removing_routes_transition),
                "STOP_FAILURE": (ContextState.REMOVING_ROUTES,
                                 self._srv_fail_remove_routes_transition),
                "STOP": (ContextState.WAITING_STOP_JOB, lambda y: None),
                "UPDATE": (ContextState.WAITING_STOP_JOB, lambda y: None)
            },
            ContextState.REVERTING_RESOLV_CONF: {
                "SUCCESS": (ContextState.SUBMITTING_STOP_JOB,
                            self._reverting_resolv_conf_transition),
                "FAIL": (ContextState.SUBMITTING_STOP_JOB,
                         self._to_removing_routes_transition)
            },
            ContextState.SUBMITTING_RESTART_JOB: {
                "SUCCESS": (ContextState.WAITING_RESTART_JOB,
                            lambda y: None),
                "FAIL": (ContextState.REVERT_RESOLV_ON_FAILED_RESTART,
                         self._submitting_restart_job_fail_transition)
            },
            ContextState.REVERT_RESOLV_ON_FAILED_RESTART: {
                "SUCCESS": (ContextState.REMOVING_ROUTES,
                            self._to_removing_routes_transition),
                "FAIL": (ContextState.REMOVING_ROUTES,
                         self._to_removing_routes_transition)
            },
            ContextState.WAITING_RESTART_JOB: {
                "RESTART_SUCCESS": (ContextState.POLLING,
                                    self._job_finished_success_transition),
                "RESTART_FAIL": (ContextState.REVERT_RESOLV_ON_FAILED_RESTART,
                                 self._waiting_restart_job_failure_transition),
                "UPDATE": (ContextState.WAITING_RESTART_JOB,
                           self._update_transition),
                "STOP": (ContextState.WAITING_TO_SUBMIT_STOP_JOB,
                         lambda y: None)
            },
            ContextState.REMOVING_ROUTES: {
                "SUCCESS": (ContextState.STOPPING, self._exit_transition),
                "FAIL": (ContextState.STOPPING, self._exit_transition)
            }
        }

    def transition_function(self, event: ContextEvent) -> bool:
        """ Perform transition based on current state and incoming event

        :param event: Incoming event
        :type event: ContextEvent
        :return: Always false. This allows use in loop callbacks
        """
        self.lgr.debug("FSM transition function called, "
                       f"state: {self.state}, event: {event.name}")
        try:
            while event is not None:
                self.state, callback \
                    = self.transition[self.state][event.name]
                event = callback(event)
                self.lgr.info(f"New state: {self.state}, new event: "
                              f"{'None' if event is None else event.name}")
        except KeyError:
            self.lgr.error("There is no transition defined from "
                           f"{self.state} on {event.name} event, ignoring")
        # a bit of a hack, so loop add functions remove this immediately
        return False

    def _starting_kickoff_transition(self, event: ContextEvent) \
            -> ContextEvent | None:
        """ Transition to CONNECTING_DBUS

        Attempt to connect to DBUS and subscribe to systemd signals

        :param event: not used
        :type event: ContextEvent
        :return: Success or FAIL with exit code
        :rtype: ContextEvent | None
        """

        self.dns_mgr = UnboundManager()
        if self.dns_mgr.configure(self.my_address, self.dnssec_enabled):
            self.lgr.info("Successfully configured DNS manager")
            return ContextEvent("SUCCESS")

        self.lgr.error("Unable to configure DNS manager")
        self._set_exit_code(ExitCode.CONFIG_FAILURE)
        return ContextEvent("FAIL")

    def _set_exit_code(self, code: ExitCode):
        if self._exit_code == 0:
            self._exit_code = code.value

    def _conf_dns_mgr_success_transition(self, event: ContextEvent) \
            -> ContextEvent | None:
        """ Transition to CONNECTING_DBUS

        Attempt to configure dns manager and its files

        :param event: not used
        :type: event: ContextEvent
        :return: SUCCESS or FAIL with exit code
        :rtype: ContextEvent | None
        """

        if (not self._connect_systemd()
                or not self._subscribe_systemd_signals()):
            self.lgr.error("Failed to connect to systemd through DBUS")
            self._set_exit_code(ExitCode.DBUS_FAILURE)
            return ContextEvent("FAIL")
        else:
            self.lgr.info("Successfully connected to systemd through DBUS")
            return ContextEvent("SUCCESS")

    def _connecting_dbus_success_transition(self, event: ContextEvent) \
            -> ContextEvent | None:
        """ Transition to SUBMITTING_START_JOB

        Attempt to connect to submit systemd start job of cache service

        :param event: not used
        :type event: ContextEvent
        :return: Success or FAIL with exit code
        :rtype: ContextEvent | None
        """
        # TODO we will configure this in network_objects
        service_start_job = self._start_unit()
        if service_start_job is None:
            self.lgr.error("Failed to submit dns cache service start job")
            self._set_exit_code(ExitCode.DBUS_FAILURE)
            return ContextEvent("FAIL")
        self._systemd_jobs[service_start_job] = (
            ContextEvent("START_OK"), ContextEvent("START_FAIL"))
        # end of part that will be configured
        self.lgr.info("Successfully submitted dns cache service start job")
        return ContextEvent("SUCCESS")

    def _service_failure_exit_transition(self, event: ContextEvent) \
            -> ContextEvent | None:
        self._set_exit_code(ExitCode.SERVICE_FAILURE)
        self.lgr.info("Stopping event loop and FSM")
        self._main_loop.quit()
        return None

    def _exit_transition(self, event: ContextEvent) -> ContextEvent | None:
        """ Transition to STOPPING

        Save exit code and stop main loop

        :param event: Event holding exit code in data
        :type event: ContextEvent
        :return: None
        :rtype: ContextEvent | None
        """
        self.lgr.info("Stopping event loop and FSM")
        self._main_loop.quit()
        return None

    def _subscribe_systemd_signals(self):
        try:
            self._systemd_manager.Subscribe()
            connection = (self._systemd_manager.
                          connect_to_signal("JobRemoved",
                                            self._on_systemd_job_finished))
            self._signal_connection = connection
            return True
        except dbus.DBusException as e:
            self.lgr.error("Systemd is not listening on " +
                           f"name org.freedesktop.systemd1 {e}")
        return False

    def _connect_systemd(self):
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

    def _on_systemd_job_finished(self, *args):
        jobid = int(args[0])
        success_event, failure_event = self._systemd_jobs.pop(jobid,
                                                              (None, None))
        if success_event is not None:
            self.lgr.debug(f"{args[2]} start job finished")
            if len(self._systemd_jobs.keys()) == 0:
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

    def _job_finished_success_transition(self, event: ContextEvent) \
            -> ContextEvent | None:
        """ Transition to POLLING

        Register timeout callback with TIMER_UP event into the main loop

        :param event: Not used
        :type event: ContextEvent
        :return: None
        :rtype: ContextEvent | None
        """
        self.lgr.info("Start job finished successfully, starting polling")
        timer_event = ContextEvent("TIMER_UP", 0)
        GLib.timeout_add_seconds(1,
                                 lambda: self.transition_function(timer_event))
        return None

    def _polling_timer_up_transition(self, event: ContextEvent) \
            -> ContextEvent | None:
        """ Transition to POLLING

        Check whether service is already running and if not then whether
        Dnsconfd is waiting too long already.

        :param event: Event with count of done polls in data
        :type event: ContextEvent
        :return: None or SERVICE_UP if service is up
        :rtype: ContextEvent | None
        """
        if not self.dns_mgr.is_ready():
            if event.data == 3:
                self.lgr.critical(f"{self.dns_mgr.service_name} did not"
                                  " respond in time, stopping dnsconfd")
                self._set_exit_code(ExitCode.SERVICE_FAILURE)
                return ContextEvent("TIMEOUT")
            self.lgr.debug(f"{self.dns_mgr.service_name} still not ready, "
                           "scheduling additional poll")
            timer = ContextEvent("TIMER_UP", event.data + 1)
            GLib.timeout_add_seconds(1,
                                     lambda: self.transition_function(timer))
            return None
        else:
            self.lgr.debug("DNS cache service is responding, "
                           "proceeding to setup of resolv.conf")
            return ContextEvent("SERVICE_UP")

    def _polling_service_up_transition(self, event: ContextEvent) \
            -> ContextEvent | None:
        """ Transition to SETTING_UP_RESOLVCONF

        Attempt to set up resolv.conf

        :param event: Not used
        :type event: ContextEvent
        :return: SUCCESS if setting up was successful otherwise FAIL
        :rtype: ContextEvent | None
        """
        if not self.sys_mgr.set_resolvconf():
            self.lgr.critical("Failed to set up resolv.conf")
            self._set_exit_code(ExitCode.RESOLV_CONF_FAILURE)
            return ContextEvent("FAIL")
        else:
            self.lgr.info("Resolv.conf successfully prepared")
            return ContextEvent("SUCCESS")

    def _running_update_transition(self, event: ContextEvent) \
            -> ContextEvent | None:
        """ Transition to UPDATING_RESOLV_CONF

        Attempt to update resolv.conf

        :param event: event with interface config in data
        :type event: ContextEvent
        :return: SUCCESS if update was successful otherwise FAIL
        :rtype: ContextEvent | None
        """
        int_config: InterfaceConfiguration = event.data
        if int_config is not None:
            if len(int_config.servers) > 0:
                self.interfaces[int_config.interface_index] = int_config
            else:
                self.interfaces.pop(int_config.interface_index, None)

        zones_to_servers, search_domains = self._get_zones_to_servers()
        if not self.sys_mgr.update_resolvconf(search_domains):
            self.lgr.critical("Failed to update resolv.conf")
            self._set_exit_code(ExitCode.SERVICE_FAILURE)
            return ContextEvent("FAIL")
        return ContextEvent("SUCCESS", zones_to_servers)

    def _get_nm_device_config(self, interface):
        int_name = interface.get_if_name(strict=True)
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
            if 40 <= device_properties["State"] < 100:
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
            self.lgr.debug(f"{e}")
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

    def _updating_resolv_conf_success_transition(self, event: ContextEvent) \
            -> ContextEvent | None:
        # here update routes and push event further, because it contains
        # zones to servers

        if not self.handle_routes:
            self.lgr.info("Config says we should not handle routes, skipping")
            return ContextEvent("SUCCESS", data=event.data)

        return self._handle_routes_process(event)

    def _remove_checked_routes(self, family, connection, valid_routes):
        modified = False
        for checked_route in list(connection[family]["route-data"]):
            if ((str(checked_route["dest"]) in self.routes.keys()) and
                (valid_routes is None or
                 str(checked_route["dest"]) not in valid_routes.keys())):
                connection[family]["route-data"].remove(checked_route)
                modified = True
                self.lgr.info(f"Removing {family} route {checked_route}")
        return modified

    def _nm_device_interface(self, ifname):
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

    def _reapply_routes(self, int_index, ifname, connection, interface_to_connection):
        self.lgr.debug("Reapplying changed connection")
        self.lgr.info(f"New ipv4 route data "
                        f"{connection["ipv4"]["route-data"]}")
        self.lgr.info(f"New ipv6 route data "
                        f"{connection["ipv6"]["route-data"]}")
        dev_int = self._nm_device_interface(ifname);
        dev_int.Reapply(connection,
                        interface_to_connection[int_index][1],
                        0)

    def _handle_routes_process(self, event: ContextEvent):

        # we need to refresh the dbus connection, because NetworkManager
        # restart would invalidate it
        try:
            self._get_nm_interface()
        except dbus.DBusException as e:
            self.lgr.error("Failed to connect to NetworkManager through DBUS,"
                           f" {e}")
            self._set_exit_code(ExitCode.ROUTE_FAILURE)
            return ContextEvent("FAIL")

        interface_and_routes = []
        interface_to_connection = {}
        self.lgr.info("Commencing route check")

        for (key, interface) in self.interfaces.items():
            ip4_rte, ip6_rte, applied = self._get_nm_device_config(interface)
            if ip4_rte is None and ip6_rte is None:
                self._set_exit_code(ExitCode.ROUTE_FAILURE)
                return ContextEvent("FAIL")
            elif applied is None:
                # we have to also remove routes of this interface,
                # so they do not interfere with further processing
                for server in interface.servers:
                    self.routes.pop(server.get_server_string(), None)
                interface_to_connection[key] = None
                continue
            for route in ip4_rte + ip6_rte:
                interface_and_routes.append((key, route))
            interface_to_connection[key] = applied

        self.lgr.debug(f"interface and routes is {interface_and_routes}")
        self.lgr.debug("interface and connections "
                       f"is {interface_to_connection}")
        valid_routes = {}
        self.lgr.debug(f"interfaces are {self.interfaces}")
        for (int_index, interface) in self.interfaces.items():
            reapply_needed = False
            ifname = interface.get_if_name()
            self.lgr.info(f"Walking through servers of interface {ifname}")
            if interface_to_connection[int_index] is None:
                # this will ensure that routes left after downed devices
                # are cleared
                continue
            # we need to remove this, so we can use route-data field
            # undocumented NetworkManager implementation detail
            del interface_to_connection[int_index][0]["ipv4"]["routes"]
            del interface_to_connection[int_index][0]["ipv6"]["routes"]
            connection = interface_to_connection[int_index][0]

            for server in interface.servers:
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
                        for route in conn["ipv4"]["route-data"]:
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
                        for x in self.interfaces[best_route[0]].servers:
                            if x == server:
                                duplicate = True
                                break
                    if duplicate:
                        # different interface also should use this server, we
                        # should handle which one of them has priority
                        other_wireless = (self.interfaces[best_route[0]]
                                          .is_interface_wireless())
                        this_wireless = interface.is_interface_wireless()
                        other_name = (self.interfaces[best_route[0]]
                                      .get_if_name())
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

            reapply_needed = self._remove_checked_routes("ipv4", connection, valid_routes) or reapply_needed
            reapply_needed = self._remove_checked_routes("ipv6", connection, valid_routes) or reapply_needed

            if reapply_needed:
                try:
                    ret = self._reapply_routes(int_index, ifname, connection, interface_to_connection)
                except dbus.DBusException as e:
                    self.lgr.error(f"Failed to reapply connection to {ifname}"
                                    f", {e}")
                    self._set_exit_code(ExitCode.ROUTE_FAILURE)
                    return ContextEvent("FAIL")

        self.routes = valid_routes
        return ContextEvent("SUCCESS", data=event.data)

    def _remove_routes(self):
        try:
            # we need to refresh the dbus connection, because NetworkManager
            # restart would invalidate it
            self._get_nm_interface()
        except dbus.DBusException:
            self.lgr.info("Failed to contact NetworkManager through dbus, "
                          "will not remove routes")
            return ContextEvent("SUCCESS")

        for (int_index, interface) in self.interfaces.items():
            reapply_needed = False
            ifname = interface.get_if_name()
            try:
                dev_int = self._nm_device_interface(ifname)
                connection, cver = dev_int.GetAppliedConnection(0)
            except dbus.DBusException:
                self.lgr.info("Failed to retrieve info about interface "
                              f" {ifname}, Will not remove its routes")
                continue

            reapply_needed = self._remove_checked_routes("ipv4", connection, None) or reapply_needed
            reapply_needed = self._remove_checked_routes("ipv6", connection, None) or reapply_needed
            if reapply_needed:
                del connection["ipv6"]["routes"]
                del connection["ipv4"]["routes"]
                # TODO: merge with _reapply_routes
                self.lgr.debug("Reapplying changed connection")
                self.lgr.info(f"New ipv4 route data "
                              f"{connection[0]["ipv4"]["route-data"]}")
                self.lgr.info(f"New ipv6 route data "
                              f"{connection[0]["ipv6"]["route-data"]}")
                try:
                    dev_int.Reapply(connection, cver, 0)
                except dbus.DBusException as e:
                    self.lgr.info(f"Failed to reapply connection of {ifname}"
                                  f", Will not remove its routes. {e}")
                    continue
        return ContextEvent("SUCCESS")

    def _srv_fail_remove_routes_transition(self, event: ContextEvent) \
            -> ContextEvent | None:
        if not self.handle_routes:
            self.lgr.info("Config says we should not handle routes, skipping")
            return ContextEvent("SUCCESS")
        self.lgr.debug("Removing routes")
        routes_str = " ".join([str(x) for x in self.routes.keys()])
        self.lgr.debug(f"routes: {routes_str}")

        self._set_exit_code(ExitCode.SERVICE_FAILURE)
        return self._remove_routes()

    def _to_removing_routes_transition(self, event: ContextEvent) \
            -> ContextEvent | None:
        if not self.handle_routes:
            self.lgr.info("Config says we should not handle routes, skipping")
            return ContextEvent("SUCCESS")
        self.lgr.debug("Removing routes")
        routes_str = " ".join([str(x) for x in self.routes.keys()])
        self.lgr.debug(f"routes: {routes_str}")
        return self._remove_routes()

    def _updating_routes_success_transition(self, event: ContextEvent) \
            -> ContextEvent | None:
        """ Transition to UPDATING_DNS_MANAGER

        Attempt to update dns caching service with new network_objects

        :param event: event with interface config in data
        :type event: ContextEvent
        :return: SUCCESS if update was successful otherwise FAIL
        :rtype: ContextEvent | None
        """
        new_zones_to_servers = event.data
        if not self.dns_mgr.update(new_zones_to_servers):
            self._set_exit_code(ExitCode.SERVICE_FAILURE)
            return ContextEvent("FAIL")
        return ContextEvent("SUCCESS")

    def _waiting_to_submit_success_transition(self, event: ContextEvent) \
            -> ContextEvent | None:
        """ Transition to SUBMITTING_STOP_JOB

        Attempt to submit stop job

        :param event: event with exit code in data
        :type event: ContextEvent
        :return: SUCCESS on success of job submission or FAIL with exit code
        :rtype: ContextEvent | None
        """
        # At this moment we did not change resolv.conf yet,
        # and we need only to wait for the start job
        # to finish and then submit stop job and wait for it to finish too
        # submitting stop job while the start is running could result in
        # unnecessary race condition
        if not self._subscribe_systemd_signals():
            self._set_exit_code(ExitCode.DBUS_FAILURE)
            return ContextEvent("FAIL")
        service_stop_job = self._stop_unit()
        if service_stop_job is None:
            self._set_exit_code(ExitCode.DBUS_FAILURE)
            return ContextEvent("FAIL")
        self._systemd_jobs[service_stop_job] = (
            ContextEvent("STOP_SUCCESS"),
            ContextEvent("STOP_FAILURE"))
        return ContextEvent("SUCCESS")

    def _updating_resolv_conf_fail_transition(self, event: ContextEvent) \
            -> ContextEvent | None:
        """ Transition to SUBMITTING_STOP_JOB

        Attempt to submit stop job

        :param event: Not used
        :type event: ContextEvent
        :return: SUCCESS or FAIL with exit code
        :rtype: ContextEvent | None
        """
        # since we have already problems with resolv.conf,
        # we will be performing this without checking result
        self._set_exit_code(ExitCode.RESOLV_CONF_FAILURE)
        self.sys_mgr.revert_resolvconf()
        if not self._subscribe_systemd_signals():
            self._set_exit_code(ExitCode.DBUS_FAILURE)
            return ContextEvent("FAIL")
        service_stop_job = self._stop_unit()
        if service_stop_job is None:
            self._set_exit_code(ExitCode.DBUS_FAILURE)
            return ContextEvent("FAIL")
        self._systemd_jobs[service_stop_job] = (
            ContextEvent("STOP_SUCCESS"),
            ContextEvent("STOP_FAILURE"))
        return ContextEvent("SUCCESS")

    def _waiting_stop_job_success_transition(self, event: ContextEvent) \
            -> ContextEvent | None:
        """ Transition to STOPPING

        Move to STOPPING state and deliver exit code

        :param event: Event with exit code in data
        :type event: ContextEvent
        :return: EXIT event with exit code
        :rtype: ContextEvent | None
        """
        self.lgr.info("Stop job after error successfully finished")
        return ContextEvent("EXIT", event.data)

    def _waiting_stop_job_fail_transition(self, event: ContextEvent) \
            -> ContextEvent | None:
        """ Transition to STOPPING

        Move to STOPPING state and deliver exit code with addition of service
        failure

        :param event: Event with exit code in data
        :type event: ContextEvent
        :return: EXIT event with exit code + service failure
        :rtype: ContextEvent | None
        """
        self.lgr.info("Stop job after error failed")
        self._set_exit_code(ExitCode.SERVICE_FAILURE)
        return ContextEvent("EXIT")

    def updating_dns_manager_fail_transition(self, event: ContextEvent) \
            -> ContextEvent | None:
        """ Transition to REVERTING_RESOLV_CONF

        Attempt to revert resolv.conf content

        :param event: Not used
        :type event: ContextEvent
        :return: SUCCESS or FAIL with exit code
        :rtype: ContextEvent | None
        """
        self.lgr.info("Failed to update DNS service, stopping")
        if not self.sys_mgr.revert_resolvconf():
            self._set_exit_code(ExitCode.RESOLV_CONF_FAILURE)
            return ContextEvent("FAIL")
        return ContextEvent("SUCCESS")

    def _reverting_resolv_conf_transition(self, event: ContextEvent) \
            -> ContextEvent | None:
        """ Transition to SUBMITTING_STOP_JOB

        Attempt to submit stop job

        :param event: Event with exit code in data
        :type event: ContextEvent
        :return: SUCCESS or FAIL with exit code
        :rtype: ContextEvent | None
        """
        if not self._subscribe_systemd_signals():
            self._set_exit_code(ExitCode.DBUS_FAILURE)
            return ContextEvent("FAIL")
        service_stop_job = self._stop_unit()
        if service_stop_job is None:
            self._set_exit_code(ExitCode.DBUS_FAILURE)
            return ContextEvent("FAIL")
        self._systemd_jobs[service_stop_job] = (
            ContextEvent("STOP_SUCCESS"),
            ContextEvent("STOP_FAILURE"))
        return ContextEvent("SUCCESS")

    def _running_stop_transition(self, event: ContextEvent) \
            -> ContextEvent | None:
        """ Transition to REVERTING_RESOLV_CONF

        Attempt to revert resolv.conf content

        :param event: Not used
        :type event: ContextEvent
        :return: SUCCESS or FAIL with exit code
        :rtype: ContextEvent | None
        """
        self.lgr.info("Stopping dnsconfd")
        if not self.sys_mgr.revert_resolvconf():
            self._set_exit_code(ExitCode.RESOLV_CONF_FAILURE)
            return ContextEvent("FAIL")
        return ContextEvent("SUCCESS")

    def _restart_failure_stop_transition(self, event: ContextEvent) \
            -> ContextEvent | None:
        self._set_exit_code(ExitCode.SERVICE_FAILURE)
        self.lgr.info("Stopping dnsconfd")
        if not self.sys_mgr.revert_resolvconf():
            return ContextEvent("FAIL")
        return ContextEvent("SUCCESS")

    def _running_reload_transition(self, event: ContextEvent) \
            -> ContextEvent | None:
        """ Transition to SUBMITTING_RESTART_JOB

        Attempt to submit restart job

        :param event: Not used
        :type event: ContextEvent
        :return: SUCCESS or FAIL with exit code
        :rtype: ContextEvent | None
        """
        self.lgr.info("Reloading DNS cache service")
        self.dns_mgr.clear_state()
        if not self._subscribe_systemd_signals():
            self._set_exit_code(ExitCode.DBUS_FAILURE)
            return ContextEvent("FAIL")
        service_restart_job = self._restart_unit()
        if service_restart_job is None:
            self._set_exit_code(ExitCode.DBUS_FAILURE)
            return ContextEvent("FAIL")
        self._systemd_jobs[service_restart_job] = (
            ContextEvent("RESTART_SUCCESS"),
            ContextEvent("RESTART_FAIL"))
        return ContextEvent("SUCCESS")

    def _setting_up_resolve_conf_transition(self, event: ContextEvent) \
            -> ContextEvent | None:
        """ Transition to SUBMITTING_RESTART_JOB

        Attempt to update resolv.conf

        :param event: Not used
        :type event: ContextEvent
        :return: SUCCESS with new zones to servers or FAIL with exit code
        :rtype: ContextEvent | None
        """
        zones_to_servers, search_domains = self._get_zones_to_servers()
        if not self.sys_mgr.update_resolvconf(search_domains):
            self.lgr.error("Failed to update resolv.conf")
            self._set_exit_code(ExitCode.SERVICE_FAILURE)
            return ContextEvent("FAIL")
        self.lgr.debug("Successfully updated resolv.conf with search domains:"
                       f"{search_domains}")
        return ContextEvent("SUCCESS", zones_to_servers)

    def _submitting_restart_job_fail_transition(self, event: ContextEvent) \
            -> ContextEvent | None:
        """ Transition to REVERTING_RESOLV_ON_FAILED_RESTART

        Attempt to revert resolv.conf

        :param event: Event with exit code in data
        :type event: ContextEvent
        :return: SUCCESS or FAIL with exit code
        :rtype: ContextEvent | None
        """
        if not self.sys_mgr.revert_resolvconf():
            self.lgr.error("Failed to revert resolv.conf")
            self._set_exit_code(ExitCode.RESOLV_CONF_FAILURE)
            return ContextEvent("FAIL")
        self.lgr.debug("Successfully reverted resolv.conf")
        return ContextEvent("SUCCESS", event.data)

    def _waiting_restart_job_failure_transition(self, event: ContextEvent) \
            -> ContextEvent | None:
        """ Transition to REVERTING_RESOLV_ON_FAILED_RESTART

        Attempt to revert resolv.conf

        :param event: Not used
        :type event: ContextEvent
        :return: SUCCESS or FAIL with exit code
        :rtype: ContextEvent | None
        """
        self._set_exit_code(ExitCode.SERVICE_FAILURE)
        if not self.sys_mgr.revert_resolvconf():
            self.lgr.error("Failed to revert resolv.conf")
            return ContextEvent("FAIL")
        self.lgr.debug("Successfully reverted resolv.conf")
        return ContextEvent("SUCCESS")

    def _update_transition(self, event: ContextEvent) \
            -> ContextEvent | None:
        """ Transition to the same state

        Save received network_objects and stay in the current state

        :param event: event with interface config in data
        :type event: ContextEvent
        :return: None
        :rtype: ContextEvent | None
        """
        if event.data is None:
            return None
        if_config: InterfaceConfiguration = event.data
        if len(if_config.servers) > 0:
            self.interfaces[if_config.interface_index] = if_config
        else:
            self.interfaces.pop(if_config.interface_index, None)
        return None

    def _start_unit(self):
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

    def _stop_unit(self):
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

    def _restart_unit(self):
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

    def _get_zones_to_servers(self):
        new_zones_to_servers = {}

        search_domains = []

        for interface in self.interfaces.values():
            self.lgr.debug(f"Processing interface {interface}")
            interface: InterfaceConfiguration
            interface_zones = []
            for dom in interface.domains:
                interface_zones.append(dom[0])
                if not dom[1]:
                    search_domains.append(dom[0])
            if interface.is_default:
                self.lgr.debug("Interface is default, appending . as its zone")
                interface_zones.append(".")
            for zone in interface_zones:
                self.lgr.debug(f"Handling zone {zone} of the interface")
                new_zones_to_servers[zone] = new_zones_to_servers.get(zone, [])
                for server in interface.servers:
                    self.lgr.debug(f"Handling server {server}")
                    found_server = []
                    for a in new_zones_to_servers[zone]:
                        if server == a:
                            found_server.append(a)
                    if len(found_server) > 0:
                        self.lgr.debug(f"Server {server} already in zone, "
                                       "handling priority")
                        prio = max(found_server[0].priority, server.priority)
                        found_server[0].priority = prio
                    else:
                        self.lgr.debug("Appending server "
                                       f"{server} to zone {zone}")
                        new_zones_to_servers[zone].append(server)

        for zone in new_zones_to_servers.keys():
            new_zones_to_servers[zone].sort(key=lambda x: (x.tls,
                                                           x.priority),
                                            reverse=True)
        for zone, servers in self.global_resolvers.items():
            self.lgr.debug(f"Adding zone {zone} from global_resolvers option")
            if zone in new_zones_to_servers.keys():
                new_zones_to_servers[zone] = (servers
                                              + new_zones_to_servers[zone])
            else:
                new_zones_to_servers[zone] = servers

        return new_zones_to_servers, search_domains

    def get_status(self, json_format: bool) -> str:
        """ Get current status of Dnsconfd

        :param json_format: True if status should be in JSON format
        :return: String with status
        :rtype: str
        """
        self.lgr.debug("Handling request for status")
        interfaces = self.interfaces.values()
        if json_format:
            status = {"service": self.dns_mgr.service_name,
                      "cache_config": self.dns_mgr.get_status(),
                      "state": self.state.name,
                      "interfaces": [a.to_dict() for a in interfaces]}
            return json.dumps(status)
        return (f"Running cache service:\n{self.dns_mgr.service_name}\n"
                "Config present in service:\n"
                f"{json.dumps(self.dns_mgr.get_status(), indent=4)}\n"
                f"State of Dnsconfd:\n{self.state.name}\n"
                "Info about interfaces: "
                f"{json.dumps([a.to_dict() for a in interfaces], indent=4)}")

    def reload_service(self) -> str:
        """ Perform reload of cache service if possible

        :return: String with answer
        :rtype: str
        """
        if self.state != ContextState.RUNNING:
            return ("Reload can not be performed at this time. "
                    + f"Current state: {self.state}")
        else:
            self.transition_function(ContextEvent("RELOAD"))
            return "Starting reload"

    def get_exit_code(self) -> int:
        """ Get exit code Dnsconfd should stop with

        :return: exit code
        :rtype: int
        """
        return self._exit_code
