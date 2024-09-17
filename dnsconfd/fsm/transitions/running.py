from dnsconfd.fsm import ContextEvent, ExitCode, ContextState
from dnsconfd.fsm.transitions.with_exit import WithExit
from dnsconfd.fsm.transitions.with_deferred_update import WithDeferredUpdate

from gi.repository import GLib


class Running(WithExit, WithDeferredUpdate):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.transitions = {
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
            ContextState.RUNNING: {
                "UPDATE": (ContextState.UPDATING_RESOLV_CONF,
                           self._running_update_transition),
                "STOP": (ContextState.REVERTING_RESOLV_CONF,
                         self._running_stop_transition),
                "RELOAD": (ContextState.SUBMITTING_RESTART_JOB,
                           self._running_reload_transition)
            },
            ContextState.SUBMITTING_RESTART_JOB: {
                "SUCCESS": (ContextState.WAITING_RESTART_JOB,
                            lambda y: None),
                "FAIL": (ContextState.REVERT_RESOLV_ON_FAILED_RESTART,
                         self._submitting_restart_job_fail_transition)
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
            }
        }

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

    def _updating_resolv_conf_success_transition(self, event: ContextEvent) \
            -> ContextEvent | None:
        # here update routes and push event further, because it contains
        # zones to servers

        if not self.container.handle_routes:
            self.lgr.info("Config says we should not handle routes, skipping")
            return ContextEvent("SUCCESS", data=event.data)

        return self.container.handle_routes_process(event)

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
        if not self.container.dns_mgr.update(new_zones_to_servers):
            self.container.set_exit_code(ExitCode.SERVICE_FAILURE)
            return ContextEvent("FAIL")
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

    def _running_update_transition(self, event: ContextEvent) \
            -> ContextEvent | None:
        """ Transition to UPDATING_RESOLV_CONF

        Attempt to update resolv.conf

        :param event: event with interface config in data
        :type event: ContextEvent
        :return: SUCCESS if update was successful otherwise FAIL
        :rtype: ContextEvent | None
        """
        if event.data is not None:
            self.container.servers = event.data

        zones_to_servers, search_domains = self.container.get_zones_to_servers()
        if not self.container.sys_mgr.update_resolvconf(search_domains):
            self.lgr.critical("Failed to update resolv.conf")
            self.container.set_exit_code(ExitCode.SERVICE_FAILURE)
            return ContextEvent("FAIL")
        return ContextEvent("SUCCESS", zones_to_servers)

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
        self.container.dns_mgr.clear_state()
        if not self.container.subscribe_systemd_signals():
            self.container.set_exit_code(ExitCode.DBUS_FAILURE)
            return ContextEvent("FAIL")
        service_restart_job = self.container.restart_unit()
        if service_restart_job is None:
            self.container.set_exit_code(ExitCode.DBUS_FAILURE)
            return ContextEvent("FAIL")
        self.container.systemd_jobs[service_restart_job] = (
            ContextEvent("RESTART_SUCCESS"),
            ContextEvent("RESTART_FAIL"))
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
