from dnsconfd.fsm import ContextEvent, ExitCode, ContextState
from dnsconfd.fsm.transitions import TransitionImplementations


class Running(TransitionImplementations):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.transitions = {
            ContextState.UPDATING_RESOLV_CONF: {
                "SUCCESS": (ContextState.UPDATING_ROUTES,
                            self._updating_resolv_conf_success_transition)
            },
            ContextState.UPDATING_ROUTES: {
                "SUCCESS": (ContextState.UPDATING_DNS_MANAGER,
                            self._updating_routes_success_transition)
            },
            ContextState.UPDATING_DNS_MANAGER: {
                "SUCCESS": (ContextState.RUNNING, lambda y: None)
            },
            ContextState.RUNNING: {
                "UPDATE": (ContextState.UPDATING_RESOLV_CONF,
                           self._running_update_transition),
                "RELOAD": (ContextState.SUBMITTING_RESTART_JOB,
                           self._running_reload_transition)
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

    def _polling_service_up_transition(self, event: ContextEvent) \
            -> ContextEvent | None:
        """ Transition to SETTING_UP_RESOLVCONF

        Attempt to set up resolv.conf

        :param event: Not used
        :type event: ContextEvent
        :return: SUCCESS if setting up was successful otherwise FAIL
        :rtype: ContextEvent | None
        """
        zones_to_servers, search_domains = self.container.get_zones_to_servers()
        if not self.container.sys_mgr.set_resolvconf(search_domains):
            self.lgr.critical("Failed to set up resolv.conf")
            self.container.set_exit_code(ExitCode.RESOLV_CONF_FAILURE)
            return ContextEvent("FAIL")

        self.lgr.info("Resolv.conf successfully prepared with "
                      f"domains: {search_domains}")
        return ContextEvent("SUCCESS", zones_to_servers)
