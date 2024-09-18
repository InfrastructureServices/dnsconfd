from dnsconfd.fsm import ContextEvent, ExitCode, ContextState
from dnsconfd.fsm.transitions import TransitionImplementations


class Stopping(TransitionImplementations):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
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
            ContextState.UPDATING_ROUTES: {
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
            }
        }

    def _to_removing_routes_transition(self, event: ContextEvent) \
            -> ContextEvent | None:
        # we have to react
        if event.name == "STOP_FAILURE":
            self.container.set_exit_code(ExitCode.SERVICE_FAILURE)
        if not self.container.handle_routes:
            self.lgr.info("Config says we should not handle routes, skipping")
            return ContextEvent("SUCCESS")
        self.lgr.debug("Removing routes")
        routes_str = " ".join([str(x) for x in self.container.routes])
        self.lgr.debug(f"routes: {routes_str}")
        return self.container.remove_routes()

    def _reverting_resolv_conf_transition(self, event: ContextEvent) \
            -> ContextEvent | None:
        """ Transition to SUBMITTING_STOP_JOB

        Attempt to submit stop job

        :param event: Event with exit code in data
        :type event: ContextEvent
        :return: SUCCESS or FAIL with exit code
        :rtype: ContextEvent | None
        """
        if not self.container.subscribe_systemd_signals():
            self.container.set_exit_code(ExitCode.DBUS_FAILURE)
            return ContextEvent("FAIL")
        service_stop_job = self.container.stop_unit()
        if service_stop_job is None:
            self.container.set_exit_code(ExitCode.DBUS_FAILURE)
            return ContextEvent("FAIL")
        self.container.systemd_jobs[service_stop_job] = (
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
        if event.name == "RESTART_FAIL":
            self.container.set_exit_code(ExitCode.SERVICE_FAILURE)
        self.lgr.info("Stopping dnsconfd")
        if not self.container.sys_mgr.revert_resolvconf():
            self.lgr.error("Failed to revert resolv.conf")
            self.container.set_exit_code(ExitCode.RESOLV_CONF_FAILURE)
            return ContextEvent("FAIL")
        self.lgr.info("Successfully reverted resolv.conf")
        return ContextEvent("SUCCESS")

    def _exit_transition(self, event: ContextEvent):
        """ Transition to STOPPING

        Save exit code and stop main loop

        :param event: Event holding exit code in data
        :type event: ContextEvent
        :return: None
        :rtype: ContextEvent | None
        """
        if event.name == "START_FAIL":
            self.container.set_exit_code(ExitCode.SERVICE_FAILURE)
        self.lgr.info("Stopping event loop and FSM")
        self.container.main_loop.quit()
        return None
