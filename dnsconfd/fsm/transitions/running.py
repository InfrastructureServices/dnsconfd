from typing import Callable
from gi.repository import GLib

from dnsconfd import SystemManager
from dnsconfd.dns_managers import UnboundManager
from dnsconfd.fsm import ContextEvent, ExitCode, ContextState
from dnsconfd.fsm.exit_code_handler import ExitCodeHandler
from dnsconfd.fsm.transitions import TransitionImplementations
from dnsconfd.routing_manager import RoutingManager
from dnsconfd.server_manager import ServerManager
from dnsconfd.systemd_manager import SystemdManager


class Running(TransitionImplementations):

    def __init__(self,
                 config: dict,
                 dns_mgr: UnboundManager,
                 exit_code_handler: ExitCodeHandler,
                 system_mgr: SystemManager,
                 systemd_manager: SystemdManager,
                 server_mgr: ServerManager,
                 route_mgr: RoutingManager,
                 transition_function: Callable):
        super().__init__(config, dns_mgr, exit_code_handler)
        self.server_manager = server_mgr
        self.sys_mgr = system_mgr
        self.systemd_mgr = systemd_manager
        self.route_mgr = route_mgr
        self.transition_function = transition_function
        self.zones_to_servers = {}
        self.search_domains = []
        self.transitions = {
            ContextState.UPDATING_RESOLV_CONF: {
                "SUCCESS": (ContextState.SUBSCRIBING_NM_CONNECTIONS,
                            self._subscribe_to_devices_connections)
            },
            ContextState.SUBSCRIBING_NM_CONNECTIONS: {
                "SUCCESS": (ContextState.CHECK_ALL_CONNECTIONS_UP,
                            self._check_all_connections_up),
                "FAIL": (ContextState.UNSUBSCRIBE_NM_AND_WAIT,
                         self.unsub_and_wait),
                "SKIP_ROUTING": (ContextState.UPDATING_DNS_MANAGER,
                                 self._updating_routes_success_transition)
            },
            ContextState.UNSUBSCRIBE_NM_AND_WAIT: {
                "SUCCESS": (ContextState.UNSUBSCRIBE_NM_AND_WAIT,
                            lambda y: None),
                "UPDATE": (ContextState.UNSUBSCRIBE_NM_AND_WAIT,
                           self.save_update_noop),
                "TIMER_UP": (ContextState.UPDATING_RESOLV_CONF,
                             self._polling_service_up_transition),
            },
            ContextState.CHECK_ALL_CONNECTIONS_UP: {
                "SUCCESS": (ContextState.GATHER_CONN_CONFIG,
                            self.gather_conn_config),
                "FAIL": (ContextState.WAIT_ALL_CONNECTIONS_UP,
                         lambda y: None),
            },
            ContextState.WAIT_ALL_CONNECTIONS_UP: {
                "INTERFACE_UP": (ContextState.CHECK_ALL_CONNECTIONS_UP,
                                 self._check_all_connections_up),
                "UPDATE": (ContextState.UNSUBSCRIBE_IMMEDIATE,
                           self.save_update_and_unsubscribe),
                "INTERFACE_DOWN": (ContextState.UNSUBSCRIBE_IMMEDIATE,
                                   self.unsubscribe_now)
            },
            ContextState.GATHER_CONN_CONFIG: {
                "SUCCESS": (ContextState.SUBSCRIBE_DHCP_CHANGES,
                            self.subscribe_dhcp_changes),
                "FAIL": (ContextState.UNSUBSCRIBE_NM_AND_WAIT,
                         self.unsub_and_wait)
            },
            ContextState.SUBSCRIBE_DHCP_CHANGES: {
                "SUCCESS": (ContextState.CHECK_ALL_DHCP_READY,
                            self.check_all_dhcp_ready),
                "FAIL": (ContextState.UNSUBSCRIBE_NM_AND_WAIT,
                         self.unsub_and_wait)
            },
            ContextState.CHECK_ALL_DHCP_READY: {
                "SUCCESS": (ContextState.MODIFY_CONNECTIONS,
                            self.modify_connections),
                "FAIL": (ContextState.WAIT_FOR_DHCP,
                         lambda y: None)
            },
            ContextState.WAIT_FOR_DHCP: {
                "DHCP_CHANGE": (ContextState.CHECK_ALL_DHCP_READY,
                                self.check_all_dhcp_ready),
                "UPDATE": (ContextState.UNSUBSCRIBE_IMMEDIATE,
                           self.save_update_and_unsubscribe),
                "INTERFACE_DOWN": (ContextState.UNSUBSCRIBE_IMMEDIATE,
                                   self.unsubscribe_now)
            },
            ContextState.UNSUBSCRIBE_IMMEDIATE: {
                "SUCCESS": (ContextState.UPDATING_RESOLV_CONF,
                            self._polling_service_up_transition)
            },
            ContextState.MODIFY_CONNECTIONS: {
                "SUCCESS": (ContextState.SUBSCRIBE_IP_CHANGES,
                            self.subscribe_ip_changes),
                "FAIL": (ContextState.UNSUBSCRIBE_NM_AND_WAIT,
                         self.unsub_and_wait)
            },
            ContextState.SUBSCRIBE_IP_CHANGES: {
                "FAIL": (ContextState.UNSUBSCRIBE_NM_AND_WAIT,
                         self.unsub_and_wait),
                "SUCCESS": (ContextState.CHECK_IP_OBJECTS,
                            self.check_ip_objs)
            },
            ContextState.CHECK_IP_OBJECTS: {
                "SUCCESS": (ContextState.UNSUBSCRIBE_IP,
                            self.unsub_only_ip),
                "FAIL": (ContextState.WAIT_IP_OBJECTS,
                         lambda y: None)
            },
            ContextState.UNSUBSCRIBE_IP: {
                "SUCCESS": (ContextState.UPDATING_DNS_MANAGER,
                            self._updating_routes_success_transition)
            },
            ContextState.WAIT_IP_OBJECTS: {
                "IP_SET": (ContextState.CHECK_IP_OBJECTS,
                           self.check_ip_objs),
                "INTERFACE_DOWN": (ContextState.UNSUBSCRIBE_IMMEDIATE,
                                   self.unsubscribe_now),
                "UPDATE": (ContextState.UNSUBSCRIBE_IMMEDIATE,
                           self.save_update_and_unsubscribe)
            },
            ContextState.UPDATING_DNS_MANAGER: {
                "SUCCESS": (ContextState.RUNNING, lambda y: None)
            },
            ContextState.RUNNING: {
                "UPDATE": (ContextState.UPDATING_RESOLV_CONF,
                           self._running_update_transition),
                "RELOAD": (ContextState.SUBMITTING_RESTART_JOB,
                           self._running_reload_transition),
                "DHCP_CHANGE": (ContextState.SUBSCRIBING_NM_CONNECTIONS,
                                self._subscribe_to_devices_connections),
                "INTERFACE_UP": (ContextState.SUBSCRIBING_NM_CONNECTIONS,
                                 self._subscribe_to_devices_connections),
                "INTERFACE_DOWN": (ContextState.SUBSCRIBING_NM_CONNECTIONS,
                                   self._subscribe_to_devices_connections),
            },
            ContextState.SUBMITTING_RESTART_JOB: {
                "SUCCESS": (ContextState.WAITING_RESTART_JOB,
                            lambda y: None)
            },
            ContextState.POLLING: {
                "SERVICE_UP": (ContextState.UPDATING_RESOLV_CONF,
                               self._polling_service_up_transition)
            }
        }

    def check_all_dhcp_ready(self, event: ContextEvent)\
            -> ContextEvent | None:
        if self.route_mgr.check_all_dhcp_ready():
            self.lgr.info("All DHCP objects ready")
            return ContextEvent("SUCCESS")
        self.lgr.info("Some DHCP objects are not yet ready, will wait")
        return ContextEvent("FAIL")

    def subscribe_dhcp_changes(self, event: ContextEvent)\
            -> ContextEvent | None:
        if self.route_mgr.subscribe_required_dhcp():
            self.lgr.info("Successfully subscribed to DHCP changes")
            return ContextEvent("SUCCESS")
        self.lgr.info("Failed to subscribe to DHCP changes, will wait")
        return ContextEvent("FAIL")

    def gather_conn_config(self, event: ContextEvent)\
            -> ContextEvent | None:
        all_servers = self.server_manager.get_all_servers()
        if self.route_mgr.gather_connections(all_servers):
            self.lgr.info("Successfully gathered connections")
            return ContextEvent("SUCCESS")
        self.lgr.info("Was not able to successfully gather connections, "
                      "will wait")
        return ContextEvent("FAIL")

    def unsub_only_ip(self, event: ContextEvent) -> ContextEvent | None:
        self.route_mgr.clear_ip_subscriptions()
        self.lgr.info("Cleared ip subscriptions")
        return ContextEvent("SUCCESS")

    def check_ip_objs(self, event: ContextEvent) -> ContextEvent | None:
        if self.route_mgr.are_all_ip_set():
            self.lgr.info("All required routes are in place, proceeding")
            return ContextEvent("SUCCESS")
        self.lgr.info("Not all required routes are in place, waiting")
        return ContextEvent("FAIL")

    def subscribe_ip_changes(self, event: ContextEvent)\
            -> ContextEvent | None:
        all_interfaces = self.server_manager.get_all_interfaces()
        if self.route_mgr.subscribe_to_ip_objs_change(all_interfaces):
            self.lgr.info("Successfully subscribed to ip changes")
            return ContextEvent("SUCCESS")
        self.lgr.info("Was not able to subscribe to ip changes, will wait")
        return ContextEvent("FAIL")

    def unsubscribe_now(self, event: ContextEvent) -> ContextEvent | None:
        self.route_mgr.clear_subscriptions()
        self.lgr.info("Successfully unsubscribed from NM events")
        return ContextEvent("SUCCESS")

    def save_update_and_unsubscribe(self, event: ContextEvent)\
            -> ContextEvent | None:
        self.server_manager.set_dynamic_servers(event.data)
        self.zones_to_servers, self.search_domains = (
            self.server_manager.get_zones_to_servers())
        self.route_mgr.clear_subscriptions()
        self.lgr.info("Successfully saved update and unsubscribed NM events")
        return ContextEvent("SUCCESS")

    def modify_connections(self, event: ContextEvent) -> ContextEvent | None:
        all_servers = self.server_manager.get_all_servers()
        if self.route_mgr.handle_routes_process(all_servers):
            self.lgr.info("Connections successfully processed")
            return ContextEvent("SUCCESS")
        self.lgr.info("Was unable to set connections into required state, "
                      "will wait")
        return ContextEvent("FAIL")

    def save_update_noop(self, event: ContextEvent) -> ContextEvent | None:
        self.server_manager.set_dynamic_servers(event.data)
        self.zones_to_servers, self.search_domains = (
            self.server_manager.get_zones_to_servers())
        self.lgr.info("Successfully saved update")
        return None

    def unsub_and_wait(self, event: ContextEvent) -> ContextEvent | None:
        self.route_mgr.clear_subscriptions()
        timer = ContextEvent("TIMER_UP", 0)
        GLib.timeout_add_seconds(1,
                                 lambda: self.transition_function(timer))
        self.lgr.info("Successfully unsubscribed from "
                      "NM events and set the timer to 1 second")
        return ContextEvent("SUCCESS")

    def _check_all_connections_up(self, event: ContextEvent)\
            -> ContextEvent | None:
        if self.route_mgr.are_all_up():
            self.lgr.debug("All connections are up, proceeding")
            return ContextEvent("SUCCESS")
        self.lgr.info("All connections are not yet up, waiting")
        return ContextEvent("FAIL")

    def _subscribe_to_devices_connections(self, event: ContextEvent)\
            -> ContextEvent | None:
        if not self.config["handle_routing"]:
            self.lgr.info("Configuration says we should not handle routing,"
                          "thus skipping it")
            return ContextEvent("SKIP_ROUTING")
        self.route_mgr.clear_subscriptions()
        all_interfaces = self.server_manager.get_all_interfaces()
        if self.route_mgr.subscribe_to_device_state_change(all_interfaces):
            self.lgr.debug("Subscribing to device state change successful")
            return ContextEvent("SUCCESS")
        self.lgr.warning("Subscribing to device state change unsuccessful, "
                         "will wait until NM is ready")
        return ContextEvent("FAIL")

    def _updating_routes_success_transition(self, event: ContextEvent) \
            -> ContextEvent | None:
        """ Transition to UPDATING_DNS_MANAGER

        Attempt to update dns caching service with new network_objects

        :param event: event with interface config in data
        :type event: ContextEvent
        :return: SUCCESS if update was successful otherwise FAIL
        :rtype: ContextEvent | None
        """
        if not self.dns_mgr.update(self.zones_to_servers):
            self.lgr.error("Failed to send update into DNS cache service")
            self.exit_code_handler.set_exit_code(ExitCode.SERVICE_FAILURE)
            return ContextEvent("FAIL")
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
        self.server_manager.set_dynamic_servers(event.data)

        self.zones_to_servers, self.search_domains = (
            self.server_manager.get_zones_to_servers())
        if not self.sys_mgr.update_resolvconf(self.search_domains):
            self.lgr.error("Failed to update resolv.conf")
            self.exit_code_handler.set_exit_code(ExitCode.SERVICE_FAILURE)
            return ContextEvent("FAIL")
        self.lgr.info("Successfully updated resolv.conf")
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
        if not self.systemd_mgr.subscribe_systemd_signals():
            self.lgr.error("Failed to subscribe to systemd signals")
            self.exit_code_handler.set_exit_code(ExitCode.DBUS_FAILURE)
            return ContextEvent("FAIL")
        jobid = self.systemd_mgr.restart_unit(self.dns_mgr.service_name,
                                              ContextEvent("RESTART_SUCCESS"),
                                              ContextEvent("RESTART_FAIL"))
        if jobid is None:
            self.lgr.error("Failed to submit service restart job")
            self.exit_code_handler.set_exit_code(ExitCode.DBUS_FAILURE)
            return ContextEvent("FAIL")
        return ContextEvent("SUCCESS")

    def _polling_service_up_transition(self, event: ContextEvent) \
            -> ContextEvent | None:
        """ Transition to SETTING_UP_RESOLVCONF

        Attempt to set up resolv.conf

        :param event: Not used
        :type event: ContextEvent
        :return: SUCCESS if setting up was successful otherwise FAIL
        :rtype: ContextEvent | None
        """
        self.zones_to_servers, self.search_domains = (
            self.server_manager.get_zones_to_servers())
        if not self.sys_mgr.set_resolvconf(self.search_domains):
            self.lgr.error("Failed to set up resolv.conf")
            self.exit_code_handler.set_exit_code(ExitCode.RESOLV_CONF_FAILURE)
            return ContextEvent("FAIL")

        self.lgr.info("Resolv.conf successfully prepared with "
                      "domains: %s", self.search_domains)
        return ContextEvent("SUCCESS")
