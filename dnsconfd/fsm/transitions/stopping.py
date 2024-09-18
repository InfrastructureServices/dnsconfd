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
                               self._service_failure_exit_transition),
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
                "FAIL": (ContextState.SUBMITTING_STOP_JOB,
                         self._updating_resolv_conf_fail_transition)
            },
            ContextState.UPDATING_ROUTES: {
                "FAIL": (ContextState.REVERTING_RESOLV_CONF,
                         self._running_stop_transition)
            },
            ContextState.UPDATING_DNS_MANAGER: {
                "FAIL": (ContextState.REVERTING_RESOLV_CONF,
                         self.updating_dns_manager_fail_transition)
            },
            ContextState.RUNNING: {
                "STOP": (ContextState.REVERTING_RESOLV_CONF,
                         self._running_stop_transition)
            },
            ContextState.SUBMITTING_RESTART_JOB: {
                "FAIL": (ContextState.REVERT_RESOLV_ON_FAILED_RESTART,
                         self._submitting_restart_job_fail_transition)
            },
            ContextState.WAITING_RESTART_JOB: {
                "RESTART_FAIL": (ContextState.REVERT_RESOLV_ON_FAILED_RESTART,
                                 self._waiting_restart_job_failure_transition),
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

    def _service_failure_exit_transition(self, event: ContextEvent) \
            -> ContextEvent | None:
        self.container.set_exit_code(ExitCode.SERVICE_FAILURE)
        self.lgr.info("Stopping event loop and FSM")
        self.container.main_loop.quit()
        return None

    def _to_removing_routes_transition(self, event: ContextEvent) \
            -> ContextEvent | None:
        if not self.container.handle_routes:
            self.lgr.info("Config says we should not handle routes, skipping")
            return ContextEvent("SUCCESS")
        self.lgr.debug("Removing routes")
        routes_str = " ".join([str(x) for x in self.container.routes])
        self.lgr.debug(f"routes: {routes_str}")
        return self.container.remove_routes()

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
        self.lgr.info("Stopping dnsconfd")
        if not self.container.sys_mgr.revert_resolvconf():
            self.container.set_exit_code(ExitCode.RESOLV_CONF_FAILURE)
            return ContextEvent("FAIL")
        return ContextEvent("SUCCESS")

    def _restart_failure_stop_transition(self, event: ContextEvent) \
            -> ContextEvent | None:
        self.container.set_exit_code(ExitCode.SERVICE_FAILURE)
        self.lgr.info("Stopping dnsconfd")
        if not self.container.sys_mgr.revert_resolvconf():
            return ContextEvent("FAIL")
        return ContextEvent("SUCCESS")

    def _srv_fail_remove_routes_transition(self, event: ContextEvent) \
            -> ContextEvent | None:
        if not self.container.handle_routes:
            self.lgr.info("Config says we should not handle routes, skipping")
            return ContextEvent("SUCCESS")
        self.lgr.debug("Removing routes")
        routes_str = " ".join([str(x) for x in self.container.routes])
        self.lgr.debug(f"routes: {routes_str}")

        self.container.set_exit_code(ExitCode.SERVICE_FAILURE)
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
        self.container.set_exit_code(ExitCode.RESOLV_CONF_FAILURE)
        self.container.sys_mgr.revert_resolvconf()
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
        if not self.container.sys_mgr.revert_resolvconf():
            self.container.set_exit_code(ExitCode.RESOLV_CONF_FAILURE)
            return ContextEvent("FAIL")
        return ContextEvent("SUCCESS")

    def _submitting_restart_job_fail_transition(self, event: ContextEvent) \
            -> ContextEvent | None:
        """ Transition to REVERTING_RESOLV_ON_FAILED_RESTART

        Attempt to revert resolv.conf

        :param event: Event with exit code in data
        :type event: ContextEvent
        :return: SUCCESS or FAIL with exit code
        :rtype: ContextEvent | None
        """
        if not self.container.sys_mgr.revert_resolvconf():
            self.lgr.error("Failed to revert resolv.conf")
            self.container.set_exit_code(ExitCode.RESOLV_CONF_FAILURE)
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
        self.container.set_exit_code(ExitCode.SERVICE_FAILURE)
        if not self.container.sys_mgr.revert_resolvconf():
            self.lgr.error("Failed to revert resolv.conf")
            return ContextEvent("FAIL")
        self.lgr.debug("Successfully reverted resolv.conf")
        return ContextEvent("SUCCESS")

    def _exit_transition(self, event: ContextEvent):
        """ Transition to STOPPING

        Save exit code and stop main loop

        :param event: Event holding exit code in data
        :type event: ContextEvent
        :return: None
        :rtype: ContextEvent | None
        """
        self.lgr.info("Stopping event loop and FSM")
        self.container.main_loop.quit()
        return None
