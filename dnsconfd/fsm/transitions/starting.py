from typing import Callable, Optional
from gi.repository import GLib

from dnsconfd import ExitCode
from dnsconfd.dns_managers import UnboundManager
from dnsconfd.fsm import ContextEvent, ContextState
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
                "UPDATE": (ContextState.WAITING_FOR_START_JOB,
                           self._update_transition)
            },
            ContextState.WAITING_RESTART_JOB: {
                "UPDATE": (ContextState.WAITING_RESTART_JOB,
                           self._update_transition)
            },
        }

    def _starting_kickoff_transition(self, event: ContextEvent):
        if self.dns_mgr.configure():
            self.lgr.info("Successfully configured DNS manager")
            return ContextEvent("SUCCESS")

        self.lgr.error("Unable to configure DNS manager")
        self.exit_code_handler.set_exit_code(ExitCode.CONFIG_FAILURE)
        return ContextEvent("FAIL")

    def _conf_dns_mgr_success_transition(self, event: ContextEvent) \
            -> Optional[ContextEvent]:
        if (not self.systemd_manager.connect_systemd()
                or not self.systemd_manager.subscribe_systemd_signals()):
            self.lgr.error("Failed to connect to systemd through DBUS")
            self.exit_code_handler.set_exit_code(ExitCode.DBUS_FAILURE)
            return ContextEvent("FAIL")
        self.lgr.info("Successfully connected to systemd through DBUS")
        return ContextEvent("SUCCESS")

    def _connecting_dbus_success_transition(self, event: ContextEvent) \
            -> Optional[ContextEvent]:
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

    def _update_transition(self, event: ContextEvent):
        self.server_manager.set_dynamic_servers(event.data[0], event.data[1])
        return None
