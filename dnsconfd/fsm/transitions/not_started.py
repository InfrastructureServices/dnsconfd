from dnsconfd.dns_managers import UnboundManager
from dnsconfd.fsm import ContextEvent, ExitCode, ContextState
from dnsconfd.fsm.transitions.with_exit import WithExit
from dnsconfd.fsm.transitions.with_deferred_update import WithDeferredUpdate


class NotStarted(WithExit, WithDeferredUpdate):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.transitions = {
            ContextState.STARTING: {
                "KICKOFF": (ContextState.CONFIGURING_DNS_MANAGER,
                            self._starting_kickoff_transition),
                "UPDATE": (ContextState.STARTING,
                           self._update_transition),
                "STOP": (ContextState.STOPPING,
                         self._exit_transition)}
        }

    def _starting_kickoff_transition(self, event: ContextEvent):
        """ Transition to CONNECTING_DBUS

        Attempt to connect to DBUS and subscribe to systemd signals

        :param event: not used
        :type event: ContextEvent
        :return: Success or FAIL with exit code
        :rtype: ContextEvent | None
        """

        self.container.dns_mgr = UnboundManager()
        address = self.container.config["listen_address"]
        dnssec = self.container.config["dnssec_enabled"]
        if self.container.dns_mgr.configure(address, dnssec):
            self.lgr.info("Successfully configured DNS manager")
            return ContextEvent("SUCCESS")

        self.lgr.error("Unable to configure DNS manager")
        self.container.set_exit_code(ExitCode.CONFIG_FAILURE)
        return ContextEvent("FAIL")
