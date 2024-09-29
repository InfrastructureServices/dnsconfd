from dnsconfd import SystemManager
from dnsconfd.dns_managers import UnboundManager
from dnsconfd.fsm import ContextEvent, ExitCode, ContextState
from dnsconfd.fsm.exit_code_handler import ExitCodeHandler
from dnsconfd.fsm.transitions import TransitionImplementations
from dnsconfd.routing_manager import RoutingManager
from dnsconfd.server_manager import ServerManager
from dnsconfd.systemd_manager import SystemdManager


class Stopping(TransitionImplementations):

    def __init__(self,
                 config: dict,
                 dns_mgr: UnboundManager,
                 exit_code_handler: ExitCodeHandler,
                 sys_mgr: SystemManager,
                 main_loop,
                 systemd_manager: SystemdManager,
                 route_mgr: RoutingManager,
                 server_mgr: ServerManager):
        """ Object responsible for stopping of Dnsconfd

        :param config: dictionary with configuration
        :param dns_mgr: dns cache manager
        :param exit_code_handler: handler of the exit code
        :param sys_mgr: system manager
        :param main_loop: GLib loop executing events
        :param systemd_manager: systemd manager
        :param route_mgr: routing manager
        :param server_mgr: server information handler
        """
        super().__init__(config, dns_mgr, exit_code_handler)
        self.sys_mgr = sys_mgr
        self.main_loop = main_loop
        self.systemd_manager = systemd_manager
        self.route_mgr = route_mgr
        self.server_mgr = server_mgr
        self.transitions = {
            ContextState.STARTING: {
                "STOP": (ContextState.STOPPING,
                         self._exit_transition)
            },
            ContextState.CONFIGURING_DNS_MANAGER: {
                "FAIL": (ContextState.STOPPING,
                         self._exit_transition)
            },
            ContextState.CONNECTING_DBUS: {
                "FAIL": (ContextState.STOPPING,
                         self._exit_transition)
            },
            ContextState.SUBMITTING_START_JOB: {
                "FAIL": (ContextState.STOPPING,
                         self._exit_transition)
            },
            ContextState.STOPPING: {
                "EXIT": (ContextState.STOPPING,
                         self._exit_transition)
            },
            ContextState.WAITING_FOR_START_JOB: {
                "START_FAIL": (ContextState.STOPPING,
                               self._exit_transition),
                "STOP": (ContextState.WAITING_TO_SUBMIT_STOP_JOB,
                         lambda y: None)
            },
            ContextState.POLLING: {
                "TIMEOUT": (ContextState.STOPPING,
                            self._exit_transition),
                "STOP": (ContextState.REVERTING_RESOLV_CONF,
                         self._running_stop_transition)
            },
            ContextState.UPDATING_RESOLV_CONF: {
                "FAIL": (ContextState.REVERTING_RESOLV_CONF,
                         self._running_stop_transition)
            },
            ContextState.UPDATING_DNS_MANAGER: {
                "FAIL": (ContextState.REVERTING_RESOLV_CONF,
                         self._running_stop_transition)
            },
            ContextState.RUNNING: {
                "STOP": (ContextState.REVERTING_RESOLV_CONF,
                         self._running_stop_transition)
            },
            ContextState.SUBMITTING_RESTART_JOB: {
                "FAIL": (ContextState.REVERT_RESOLV_ON_FAILED_RESTART,
                         self._running_stop_transition)
            },
            ContextState.WAITING_RESTART_JOB: {
                "RESTART_FAIL": (ContextState.REVERT_RESOLV_ON_FAILED_RESTART,
                                 self._running_stop_transition),
                "STOP": (ContextState.WAITING_TO_SUBMIT_STOP_JOB,
                         lambda y: None)
            },
            ContextState.WAITING_TO_SUBMIT_STOP_JOB: {
                "START_OK": (ContextState.SUBMITTING_STOP_JOB,
                             self._reverting_resolv_conf_transition),
                "START_FAIL": (ContextState.REMOVING_ROUTES,
                               self._to_removing_routes_transition),
                "STOP": (ContextState.WAITING_TO_SUBMIT_STOP_JOB,
                         lambda y: None),
                "UPDATE": (ContextState.WAITING_TO_SUBMIT_STOP_JOB,
                           lambda y: None),
                "RESTART_SUCCESS": (ContextState.REVERTING_RESOLV_CONF,
                                    self._running_stop_transition),
                "RESTART_FAIL": (ContextState.REVERTING_RESOLV_CONF,
                                 self._running_stop_transition)
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
                                 self._to_removing_routes_transition),
                "STOP": (ContextState.WAITING_STOP_JOB, lambda y: None),
                "UPDATE": (ContextState.WAITING_STOP_JOB, lambda y: None)
            },
            ContextState.REVERTING_RESOLV_CONF: {
                "SUCCESS": (ContextState.SUBMITTING_STOP_JOB,
                            self._reverting_resolv_conf_transition),
                "FAIL": (ContextState.SUBMITTING_STOP_JOB,
                         self._reverting_resolv_conf_transition)
            },
            ContextState.REVERT_RESOLV_ON_FAILED_RESTART: {
                "SUCCESS": (ContextState.REMOVING_ROUTES,
                            self._to_removing_routes_transition),
                "FAIL": (ContextState.REMOVING_ROUTES,
                         self._to_removing_routes_transition)
            },
            ContextState.REMOVING_ROUTES: {
                "SUCCESS": (ContextState.STOPPING, self._exit_transition),
                "FAIL": (ContextState.STOPPING, self._exit_transition)
            },
            ContextState.UNSUBSCRIBE_NM_AND_WAIT: {
                "STOP": (ContextState.REVERTING_RESOLV_CONF,
                         self._running_stop_transition)
            },
            ContextState.WAIT_ALL_CONNECTIONS_UP: {
                "STOP": (ContextState.REVERTING_RESOLV_CONF,
                         self._running_stop_transition)
            },
            ContextState.WAIT_IP_OBJECTS: {
                "STOP": (ContextState.REVERTING_RESOLV_CONF,
                         self._running_stop_transition)
            },
            ContextState.WAIT_FOR_DHCP: {
                "STOP": (ContextState.REVERTING_RESOLV_CONF,
                         self._running_stop_transition)
            }
        }

    def _to_removing_routes_transition(self, event: ContextEvent) \
            -> ContextEvent | None:
        # we have to react
        if event.name == "STOP_FAILURE":
            self.exit_code_handler.set_exit_code(ExitCode.SERVICE_FAILURE)
        if not self.config["handle_routing"]:
            self.lgr.info("Config says we should not handle routes, skipping")
            return ContextEvent("SUCCESS")
        self.lgr.debug("Removing routes")
        self.route_mgr.remove_routes()
        return ContextEvent("SUCCESS")

    def _reverting_resolv_conf_transition(self, event: ContextEvent) \
            -> ContextEvent | None:
        if not self.systemd_manager.subscribe_systemd_signals():
            self.exit_code_handler.set_exit_code(ExitCode.DBUS_FAILURE)
            return ContextEvent("FAIL")
        jobid = self.systemd_manager.change_unit_state(
            2,
            self.dns_mgr.service_name,
            ContextEvent("STOP_SUCCESS"),
            ContextEvent("STOP_FAILURE"))
        if jobid is None:
            self.exit_code_handler.set_exit_code(ExitCode.DBUS_FAILURE)
            return ContextEvent("FAIL")
        return ContextEvent("SUCCESS")

    def _running_stop_transition(self, event: ContextEvent) \
            -> ContextEvent | None:
        if event.name == "RESTART_FAIL":
            self.exit_code_handler.set_exit_code(ExitCode.SERVICE_FAILURE)
        self.lgr.info("Stopping dnsconfd")
        if not self.sys_mgr.revert_resolvconf():
            self.lgr.error("Failed to revert resolv.conf")
            self.exit_code_handler.set_exit_code(ExitCode.RESOLV_CONF_FAILURE)
            return ContextEvent("FAIL")
        self.lgr.info("Successfully reverted resolv.conf")
        return ContextEvent("SUCCESS")

    def _exit_transition(self, event: ContextEvent):
        if event.name == "START_FAIL":
            self.exit_code_handler.set_exit_code(ExitCode.SERVICE_FAILURE)
        self.lgr.info("Stopping event loop and FSM")
        self.main_loop.quit()
        return None
