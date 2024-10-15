from typing import Callable
from gi.repository import GLib

from dnsconfd import SystemManager, ExitCode
from dnsconfd.dns_managers import UnboundManager
from dnsconfd.fsm import ContextEvent, ContextState
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
        """ Object responsible for performing running stage of Dnsconfd

        :param config: dictionary with configuration
        :param dns_mgr: dns cache manager
        :param exit_code_handler: handler of the exit code
        :param system_mgr: system manager
        :param systemd_manager: systemd manager
        :param server_mgr: handler of server information
        :param route_mgr: manager of routing
        :param transition_function: function to be called when transition is
        necessary
        """
        super().__init__(config, dns_mgr, exit_code_handler)
        self.server_manager = server_mgr
        self.sys_mgr = system_mgr
        self.systemd_mgr = systemd_manager
        self.route_mgr = route_mgr
        self.transition_function = transition_function
        self.routed_servers = []
        self.zones_to_servers = {}
        self.transitions = {
            ContextState.SUBSCRIBING_NM_CONNECTIONS: {
                "SUCCESS": (ContextState.CHECK_ALL_CONNECTIONS_UP,
                            self._check_all_connections_up),
                "FAIL": (ContextState.UNSUBSCRIBE_NM_AND_WAIT,
                         self._unsub_and_wait),
                "SKIP_ROUTING": (ContextState.UPDATING_RESOLV_CONF,
                                 self._update_resolv_conf)
            },
            ContextState.UNSUBSCRIBE_NM_AND_WAIT: {
                "SUCCESS": (ContextState.UNSUBSCRIBE_NM_AND_WAIT,
                            lambda y: None),
                "UPDATE": (ContextState.UNSUBSCRIBE_NM_AND_WAIT,
                           self._save_update_noop),
                "TIMER_UP": (ContextState.SUBSCRIBING_NM_CONNECTIONS,
                             self._subscribe_to_devices_connections),
            },
            ContextState.CHECK_ALL_CONNECTIONS_UP: {
                "SUCCESS": (ContextState.GATHER_CONN_CONFIG,
                            self._gather_conn_config),
                "FAIL": (ContextState.WAIT_ALL_CONNECTIONS_UP,
                         lambda y: None),
            },
            ContextState.WAIT_ALL_CONNECTIONS_UP: {
                "INTERFACE_UP": (ContextState.CHECK_ALL_CONNECTIONS_UP,
                                 self._check_all_connections_up),
                "UPDATE": (ContextState.UNSUBSCRIBE_IMMEDIATE,
                           self._save_update_and_unsubscribe),
                "INTERFACE_DOWN": (ContextState.UNSUBSCRIBE_IMMEDIATE,
                                   self._unsubscribe_now)
            },
            ContextState.UNSUBSCRIBE_IMMEDIATE: {
                "SUCCESS": (ContextState.SUBSCRIBING_NM_CONNECTIONS,
                            self._subscribe_to_devices_connections)
            },
            ContextState.GATHER_CONN_CONFIG: {
                "SUCCESS": (ContextState.SUBSCRIBE_IP_CHANGES,
                            self._subscribe_ip_changes),
                "FAIL": (ContextState.UNSUBSCRIBE_NM_AND_WAIT,
                         self._unsub_and_wait)
            },
            ContextState.SUBSCRIBE_IP_CHANGES: {
                "FAIL": (ContextState.UNSUBSCRIBE_NM_AND_WAIT,
                         self._unsub_and_wait),
                "SUCCESS": (ContextState.CHECK_IP_OBJECTS,
                            self._check_ip_objs)
            },
            ContextState.CHECK_IP_OBJECTS: {
                "SUCCESS": (ContextState.MODIFY_CONNECTIONS,
                            self._modify_connections),
                "FAIL": (ContextState.WAIT_IP_OBJECTS,
                         lambda y: None)
            },
            ContextState.WAIT_IP_OBJECTS: {
                "IP_READY": (ContextState.CHECK_IP_OBJECTS,
                             self._check_ip_objs),
                "IP_NOT_READY": (ContextState.WAIT_IP_OBJECTS,
                                 lambda y: None),
                "INTERFACE_DOWN": (ContextState.UNSUBSCRIBE_IMMEDIATE,
                                   self._unsubscribe_now),
                "UPDATE": (ContextState.UNSUBSCRIBE_IMMEDIATE,
                           self._save_update_and_unsubscribe),
            },
            ContextState.MODIFY_CONNECTIONS: {
                "CHANGE": (ContextState.UNSUBSCRIBE_IMMEDIATE,
                           self._unsubscribe_now),
                "NO_CHANGE": (ContextState.REMOVE_REDUNDANT_ROUTES,
                              self._remove_redundant),
                "FAIL": (ContextState.UNSUBSCRIBE_NM_AND_WAIT,
                         self._unsub_and_wait)
            },
            ContextState.REMOVE_REDUNDANT_ROUTES: {
                "SUCCESS": (ContextState.UPDATING_RESOLV_CONF,
                            self._update_resolv_conf),
                "FAIL": (ContextState.UNSUBSCRIBE_NM_AND_WAIT,
                         self._unsub_and_wait)
            },
            ContextState.UPDATING_DNS_MANAGER: {
                "SUCCESS": (ContextState.RUNNING, lambda y: None)
            },
            ContextState.RUNNING: {
                "UPDATE": (ContextState.UNSUBSCRIBE_IMMEDIATE,
                           self._save_update_and_unsubscribe),
                "RELOAD": (ContextState.SUBMITTING_RESTART_JOB,
                           self._running_reload_transition),
                "INTERFACE_UP": (ContextState.SUBSCRIBING_NM_CONNECTIONS,
                                 self._subscribe_to_devices_connections),
                "INTERFACE_DOWN": (ContextState.SUBSCRIBING_NM_CONNECTIONS,
                                   self._subscribe_to_devices_connections),
                "IP_READY": (ContextState.SUBSCRIBING_NM_CONNECTIONS,
                             self._subscribe_to_devices_connections),
                "IP_NOT_READY": (ContextState.SUBSCRIBING_NM_CONNECTIONS,
                                 self._subscribe_to_devices_connections),
            },
            ContextState.SUBMITTING_RESTART_JOB: {
                "SUCCESS": (ContextState.WAITING_RESTART_JOB,
                            lambda y: None)
            },
            ContextState.POLLING: {
                "SERVICE_UP": (ContextState.SETTING_RESOLV_CONF,
                               self._set_resolv_conf)
            },
            ContextState.SETTING_RESOLV_CONF: {
                "SUCCESS": (ContextState.SUBSCRIBING_NM_CONNECTIONS,
                            self._subscribe_to_devices_connections)
            },
            ContextState.UPDATING_RESOLV_CONF: {
                "SUCCESS": (ContextState.UPDATING_DNS_MANAGER,
                            self._updating_routes_success_transition)
            }
        }

    def _remove_redundant(self, event: ContextEvent) -> ContextEvent | None:
        self.lgr.info("Removing redundant routes")
        if self.route_mgr.remove_redundant():
            self.lgr.info("Removed redundant routes, will proceed")
            return ContextEvent("SUCCESS")
        self.lgr.info("Failed to remove redundant routes, will wait")
        return ContextEvent("FAIL")

    def _gather_conn_config(self, event: ContextEvent) \
            -> ContextEvent | None:
        if self.route_mgr.gather_connections():
            self.lgr.info("Successfully gathered connections")
            return ContextEvent("SUCCESS")
        self.lgr.info("Was not able to successfully gather connections, "
                      "will wait")
        return ContextEvent("FAIL")

    def _check_ip_objs(self, event: ContextEvent) -> ContextEvent | None:
        if self.route_mgr.is_any_ip_object_ready():
            self.lgr.info("At least one ip object is ready for routing, "
                          "proceeding")
            return ContextEvent("SUCCESS")
        self.lgr.info("None of the watched ip objects are ready, waiting")
        return ContextEvent("FAIL")

    def _subscribe_ip_changes(self, event: ContextEvent) \
            -> ContextEvent | None:
        if self.route_mgr.subscribe_to_ip_objs_change():
            self.lgr.info("Successfully subscribed to ip changes")
            return ContextEvent("SUCCESS")
        self.lgr.info("Was not able to subscribe to ip changes, will wait")
        return ContextEvent("FAIL")

    def _unsubscribe_now(self, event: ContextEvent) -> ContextEvent | None:
        self.route_mgr.clear_transaction()
        self.lgr.info("Successfully unsubscribed from NM events")
        return ContextEvent("SUCCESS")

    def _save_update_and_unsubscribe(self, event: ContextEvent) \
            -> ContextEvent | None:
        self.server_manager.set_dynamic_servers(event.data[0], event.data[1])
        self.route_mgr.clear_transaction()
        self.lgr.info("Successfully saved update and unsubscribed NM events")
        return ContextEvent("SUCCESS")

    def _modify_connections(self, event: ContextEvent) -> ContextEvent | None:
        routed_servers, change = self.route_mgr.handle_routes_process()
        if change == 0:
            self.lgr.info("No change of routing was needed, proceeding")
            self.routed_servers = routed_servers
            return ContextEvent("NO_CHANGE")
        elif change == 1:
            self.lgr.info("We submitted changes to connections, "
                          "will wait for them to take effect")
            return ContextEvent("CHANGE")
        self.lgr.info("Issue was encountered when changing routing, will wait")
        return ContextEvent("FAIL")

    def _save_update_noop(self, event: ContextEvent) -> ContextEvent | None:
        self.server_manager.set_dynamic_servers(event.data[0], event.data[1])
        self.lgr.info("Successfully saved update")
        return None

    def _unsub_and_wait(self, event: ContextEvent) -> ContextEvent | None:
        self.route_mgr.clear_transaction()
        timer = ContextEvent("TIMER_UP", 0)
        GLib.timeout_add_seconds(1,
                                 lambda: self.transition_function(timer))
        self.lgr.info("Successfully unsubscribed from "
                      "NM events and set the timer to 1 second")
        return ContextEvent("SUCCESS")

    def _check_all_connections_up(self, event: ContextEvent) \
            -> ContextEvent | None:
        if self.route_mgr.are_all_up():
            self.lgr.debug("All connections are up, proceeding")
            return ContextEvent("SUCCESS")
        self.lgr.info("All connections are not yet up, waiting")
        return ContextEvent("FAIL")

    def _subscribe_to_devices_connections(self, event: ContextEvent) \
            -> ContextEvent | None:
        servers = self.server_manager.get_used_servers()
        if not self.config["handle_routing"]:
            self.lgr.info("Configuration says we should not handle routing,"
                          "thus skipping it")
            self.routed_servers = servers
            return ContextEvent("SKIP_ROUTING")
        self.route_mgr.clear_transaction()
        if self.route_mgr.subscribe_to_device_state_change(servers):
            self.lgr.debug("Subscribing to device state change successful")
            return ContextEvent("SUCCESS")
        self.lgr.warning("Subscribing to device state change unsuccessful, "
                         "will wait until NM is ready")
        return ContextEvent("FAIL")

    def _updating_routes_success_transition(self, event: ContextEvent) \
            -> ContextEvent | None:
        if not self.dns_mgr.update(self.zones_to_servers):
            self.lgr.error("Failed to send update into DNS cache service")
            self.exit_code_handler.set_exit_code(ExitCode.SERVICE_FAILURE)
            return ContextEvent("FAIL")
        return ContextEvent("SUCCESS")

    def _running_reload_transition(self, event: ContextEvent) \
            -> ContextEvent | None:
        self.lgr.info("Reloading DNS cache service")
        self.dns_mgr.clear_state()
        if not self.systemd_mgr.subscribe_systemd_signals():
            self.lgr.error("Failed to subscribe to systemd signals")
            self.exit_code_handler.set_exit_code(ExitCode.DBUS_FAILURE)
            return ContextEvent("FAIL")
        jobid = self.systemd_mgr.change_unit_state(
            1,
            self.dns_mgr.service_name,
            ContextEvent("RESTART_SUCCESS"),
            ContextEvent("RESTART_FAIL"))
        if jobid is None:
            self.lgr.error("Failed to submit service restart job")
            self.exit_code_handler.set_exit_code(ExitCode.DBUS_FAILURE)
            return ContextEvent("FAIL")
        return ContextEvent("SUCCESS")

    def _update_resolv_conf(self, event: ContextEvent) \
            -> ContextEvent | None:
        self.zones_to_servers, search_domains = (
            self.server_manager.get_zones_to_servers(self.routed_servers))
        if not self.sys_mgr.update_resolvconf(search_domains):
            self.lgr.error("Failed to update resolv.conf")
            self.exit_code_handler.set_exit_code(ExitCode.RESOLV_CONF_FAILURE)
            return ContextEvent("FAIL")
        self.lgr.info("Resolv.conf successfully updated")
        return ContextEvent("SUCCESS")

    def _set_resolv_conf(self, event: ContextEvent) -> ContextEvent | None:
        if not self.sys_mgr.set_resolvconf():
            self.lgr.error("Failed to set resolv.conf")
            self.exit_code_handler.set_exit_code(ExitCode.RESOLV_CONF_FAILURE)
            return ContextEvent("FAIL")
        self.lgr.info("Resolv.conf successfully set up")
        return ContextEvent("SUCCESS")
