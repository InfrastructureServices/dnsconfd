from typing import Callable
from gi.repository import GLib

from dnsconfd.dns_managers import UnboundManager
from dnsconfd.fsm import ContextEvent, ExitCode, ContextState
from dnsconfd.fsm.exit_code_handler import ExitCodeHandler
from dnsconfd.fsm.transitions import TransitionImplementations
from dnsconfd.server_manager import ServerManager
from dnsconfd.systemd_manager import SystemdManager


class Starting(TransitionImplementations):

    def __init__(self,
                 config: dict,
                 dns_mgr: UnboundManager,
                 exit_code_handler: ExitCodeHandler,
                 transition_function: Callable,
                 systemd_manager: SystemdManager,
                 server_mgr: ServerManager):
        """ Object responsible for start of Dnsconfd

        :param config: dictionary with configuration
        :param dns_mgr: dns cache manager
        :param exit_code_handler: handler of the exit code
        :param transition_function: function to be called when transition is
        necessary
        :param systemd_manager: systemd manager
        :param server_mgr: handler of server information
        """
        super().__init__(config, dns_mgr, exit_code_handler)
        self.systemd_manager = systemd_manager
        self.server_manager = server_mgr
        self.transition_function = transition_function
        self.transitions = {
            ContextState.STARTING: {
                "KICKOFF": (ContextState.CONFIGURING_DNS_MANAGER,
                            self._starting_kickoff_transition),
                "UPDATE": (ContextState.STARTING,
                           self._update_transition)
            },
            ContextState.CONFIGURING_DNS_MANAGER: {
                "SUCCESS": (ContextState.CONNECTING_DBUS,
                            self._conf_dns_mgr_success_transition)
            },
            ContextState.CONNECTING_DBUS: {
                "SUCCESS": (ContextState.SUBMITTING_START_JOB,
                            self._connecting_dbus_success_transition)
            },
            ContextState.SUBMITTING_START_JOB: {
                "SUCCESS": (ContextState.WAITING_FOR_START_JOB,
                            lambda y: None)
            },
            ContextState.WAITING_FOR_START_JOB: {
                "START_OK": (ContextState.POLLING,
                             self._job_finished_success_transition),
                "UPDATE": (ContextState.WAITING_FOR_START_JOB,
                           self._update_transition)
            },
            ContextState.POLLING: {
                "TIMER_UP": (ContextState.POLLING,
                             self._polling_timer_up_transition),
                "UPDATE": (ContextState.POLLING,
                           self._update_transition)
            },
            ContextState.WAITING_RESTART_JOB: {
                "RESTART_SUCCESS": (ContextState.POLLING,
                                    self._job_finished_success_transition),
                "UPDATE": (ContextState.WAITING_RESTART_JOB,
                           self._update_transition)
            },
        }

    def _starting_kickoff_transition(self, event: ContextEvent):
        address = self.config["listen_address"]
        if self.dns_mgr.configure(address):
            self.lgr.info("Successfully configured DNS manager")
            return ContextEvent("SUCCESS")

        self.lgr.error("Unable to configure DNS manager")
        self.exit_code_handler.set_exit_code(ExitCode.CONFIG_FAILURE)
        return ContextEvent("FAIL")

    def _conf_dns_mgr_success_transition(self, event: ContextEvent) \
            -> ContextEvent | None:
        if (not self.systemd_manager.connect_systemd()
                or not self.systemd_manager.subscribe_systemd_signals()):
            self.lgr.error("Failed to connect to systemd through DBUS")
            self.exit_code_handler.set_exit_code(ExitCode.DBUS_FAILURE)
            return ContextEvent("FAIL")
        self.lgr.info("Successfully connected to systemd through DBUS")
        return ContextEvent("SUCCESS")

    def _connecting_dbus_success_transition(self, event: ContextEvent) \
            -> ContextEvent | None:
        # TODO we will configure this in network_objects
        service_start_job = (
            self.systemd_manager.change_unit_state(
                0,
                self.dns_mgr.service_name,
                ContextEvent("START_OK"),
                ContextEvent("START_FAIL")))
        if service_start_job is None:
            self.lgr.error("Failed to submit dns cache service start job")
            self.exit_code_handler.set_exit_code(ExitCode.DBUS_FAILURE)
            return ContextEvent("FAIL")
        # end of part that will be configured
        self.lgr.info("Successfully submitted dns cache service start job")
        return ContextEvent("SUCCESS")

    def _job_finished_success_transition(self, event: ContextEvent) \
            -> ContextEvent | None:
        self.lgr.info("Start job finished successfully, starting polling")
        timer = ContextEvent("TIMER_UP", 0)
        GLib.timeout_add_seconds(1,
                                 lambda: self.transition_function(timer))
        return None

    def _polling_timer_up_transition(self, event: ContextEvent) \
            -> ContextEvent | None:
        if not self.dns_mgr.is_ready():
            if event.data == 3:
                self.lgr.critical("%s did not "
                                  "respond in time, stopping dnsconfd",
                                  self.dns_mgr.service_name)
                self.exit_code_handler.set_exit_code(ExitCode.SERVICE_FAILURE)
                return ContextEvent("TIMEOUT")
            self.lgr.debug("%s still not ready, "
                           "scheduling additional poll",
                           self.dns_mgr.service_name)
            timer = ContextEvent("TIMER_UP", event.data + 1)
            GLib.timeout_add_seconds(1,
                                     lambda: self.transition_function(timer))
            return None
        self.lgr.debug("DNS cache service is responding, "
                       "proceeding to setup of resolv.conf")
        return ContextEvent("SERVICE_UP")

    def _update_transition(self, event: ContextEvent):
        if event.data is None:
            return None
        self.server_manager.set_dynamic_servers(event.data)
        return None
