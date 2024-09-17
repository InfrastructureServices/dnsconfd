from dnsconfd.fsm import ContextEvent, ExitCode, ContextState
from dnsconfd.fsm.transitions.with_exit import WithExit
from dnsconfd.fsm.transitions.with_deferred_update import WithDeferredUpdate

from gi.repository import GLib


class Starting(WithExit, WithDeferredUpdate):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.transitions = {
            ContextState.CONFIGURING_DNS_MANAGER: {
                "SUCCESS": (ContextState.CONNECTING_DBUS,
                            self._conf_dns_mgr_success_transition),
                "FAIL": (ContextState.STOPPING,
                         self._exit_transition)
            },
            ContextState.CONNECTING_DBUS: {
                "FAIL": (ContextState.STOPPING,
                         self._exit_transition),
                "SUCCESS": (ContextState.SUBMITTING_START_JOB,
                            self._connecting_dbus_success_transition)
            },
            ContextState.SUBMITTING_START_JOB: {
                "FAIL": (ContextState.STOPPING,
                         self._exit_transition),
                "SUCCESS": (ContextState.WAITING_FOR_START_JOB,
                            lambda y: None)
            },
            ContextState.WAITING_FOR_START_JOB: {
                "START_OK": (ContextState.POLLING,
                             self._job_finished_success_transition),
                "START_FAIL": (ContextState.STOPPING,
                               self._service_failure_exit_transition),
                "UPDATE": (ContextState.WAITING_FOR_START_JOB,
                           self._update_transition),
                "STOP": (ContextState.WAITING_TO_SUBMIT_STOP_JOB,
                         lambda y: None)
            },
            ContextState.POLLING: {
                "TIMER_UP": (ContextState.POLLING,
                             self._polling_timer_up_transition),
                "SERVICE_UP": (ContextState.SETTING_UP_RESOLVCONF,
                               self._polling_service_up_transition),
                "TIMEOUT": (ContextState.STOPPING,
                            self._exit_transition),
                "UPDATE": (ContextState.POLLING,
                           self._update_transition),
                "STOP": (ContextState.REVERTING_RESOLV_CONF,
                         self._running_stop_transition)
            },
            ContextState.SETTING_UP_RESOLVCONF: {
                "FAIL": (ContextState.STOPPING,
                         self._exit_transition),
                "SUCCESS": (ContextState.UPDATING_RESOLV_CONF,
                            self._setting_up_resolve_conf_transition)
            }
        }

    def _conf_dns_mgr_success_transition(self, event: ContextEvent) \
            -> ContextEvent | None:
        """ Transition to CONNECTING_DBUS

        Attempt to configure dns manager and its files

        :param event: not used
        :type: event: ContextEvent
        :return: SUCCESS or FAIL with exit code
        :rtype: ContextEvent | None
        """

        if (not self.container.connect_systemd()
                or not self.container.subscribe_systemd_signals()):
            self.lgr.error("Failed to connect to systemd through DBUS")
            self.container.set_exit_code(ExitCode.DBUS_FAILURE)
            return ContextEvent("FAIL")
        else:
            self.lgr.info("Successfully connected to systemd through DBUS")
            return ContextEvent("SUCCESS")

    def _connecting_dbus_success_transition(self, event: ContextEvent) \
            -> ContextEvent | None:
        """ Transition to SUBMITTING_START_JOB

        Attempt to connect to submit systemd start job of cache service

        :param event: not used
        :type event: ContextEvent
        :return: Success or FAIL with exit code
        :rtype: ContextEvent | None
        """
        # TODO we will configure this in network_objects
        service_start_job = self.container.start_unit()
        if service_start_job is None:
            self.lgr.error("Failed to submit dns cache service start job")
            self.container.set_exit_code(ExitCode.DBUS_FAILURE)
            return ContextEvent("FAIL")
        self.container.systemd_jobs[service_start_job] = (
            ContextEvent("START_OK"), ContextEvent("START_FAIL"))
        # end of part that will be configured
        self.lgr.info("Successfully submitted dns cache service start job")
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

    def _service_failure_exit_transition(self, event: ContextEvent) \
            -> ContextEvent | None:
        self.container.set_exit_code(ExitCode.SERVICE_FAILURE)
        self.lgr.info("Stopping event loop and FSM")
        self.container.main_loop.quit()
        return None

    def _polling_timer_up_transition(self, event: ContextEvent) \
            -> ContextEvent | None:
        """ Transition to POLLING

        Check whether service is already running and if not then whether
        Dnsconfd is waiting too long already.

        :param event: Event with count of done polls in data
        :type event: ContextEvent
        :return: None or SERVICE_UP if service is up
        :rtype: ContextEvent | None
        """
        if not self.container.dns_mgr.is_ready():
            if event.data == 3:
                self.lgr.critical(f"{self.container.dns_mgr.service_name} did not"
                                  " respond in time, stopping dnsconfd")
                self.container.set_exit_code(ExitCode.SERVICE_FAILURE)
                return ContextEvent("TIMEOUT")
            self.lgr.debug(f"{self.container.dns_mgr.service_name} still not ready, "
                           "scheduling additional poll")
            timer = ContextEvent("TIMER_UP", event.data + 1)
            GLib.timeout_add_seconds(1,
                                     lambda: self.transition_function(timer))
            return None
        else:
            self.lgr.debug("DNS cache service is responding, "
                           "proceeding to setup of resolv.conf")
            return ContextEvent("SERVICE_UP")

    def _polling_service_up_transition(self, event: ContextEvent) \
            -> ContextEvent | None:
        """ Transition to SETTING_UP_RESOLVCONF

        Attempt to set up resolv.conf

        :param event: Not used
        :type event: ContextEvent
        :return: SUCCESS if setting up was successful otherwise FAIL
        :rtype: ContextEvent | None
        """
        if not self.container.sys_mgr.set_resolvconf():
            self.lgr.critical("Failed to set up resolv.conf")
            self.container.set_exit_code(ExitCode.RESOLV_CONF_FAILURE)
            return ContextEvent("FAIL")
        else:
            self.lgr.info("Resolv.conf successfully prepared")
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

    def _setting_up_resolve_conf_transition(self, event: ContextEvent) \
            -> ContextEvent | None:
        """ Transition to SUBMITTING_RESTART_JOB

        Attempt to update resolv.conf

        :param event: Not used
        :type event: ContextEvent
        :return: SUCCESS with new zones to servers or FAIL with exit code
        :rtype: ContextEvent | None
        """
        zones_to_servers, search_domains = self.container.get_zones_to_servers()
        if not self.container.sys_mgr.update_resolvconf(search_domains):
            self.lgr.error("Failed to update resolv.conf")
            self.container.set_exit_code(ExitCode.SERVICE_FAILURE)
            return ContextEvent("FAIL")
        self.lgr.debug("Successfully updated resolv.conf with search domains:"
                       f"{search_domains}")
        return ContextEvent("SUCCESS", zones_to_servers)
