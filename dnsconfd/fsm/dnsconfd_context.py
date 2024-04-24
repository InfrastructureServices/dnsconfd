from dnsconfd.network_objects import InterfaceConfiguration
from dnsconfd.dns_managers import UnboundManager
from dnsconfd.fsm import ContextEvent
from dnsconfd.fsm import ContextState
from dnsconfd import SystemManager
from dnsconfd.fsm import ExitCode

from gi.repository import GLib
from typing import Callable
import logging as lgr
import dbus.service
import json
from enum import Enum

class DnsconfdContext:
    def __init__(self, config: dict, main_loop: object):
        """ Class containing implementation of FSM that controls Dnsconfd
        operations

        :param config: dict containing network_objects
        :type config: dict
        :param main_loop: Main loop provided by GLib
        :type main_loop: object
        """
        self.my_address = config["listen_address"]
        self.sys_mgr = SystemManager(config)
        self._main_loop = main_loop

        self._systemd_object = None

        self.dns_mgr = None
        self.interfaces: dict[int, InterfaceConfiguration] = {}

        # dictionary, systemd jobs -> event that should be emitted on success,
        # event that should be emitted on failure
        self._systemd_jobs: dict[int, tuple[ContextEvent, ContextEvent]] = {}
        self._exit_code = 0
        self.state = ContextState.STARTING
        self.transition: dict[
            ContextState,
            dict[str,
                 tuple[ContextState,
                       Callable[[DnsconfdContext, ContextEvent],
                                ContextEvent]]]] = {
            ContextState.STARTING: {
                "KICKOFF": (ContextState.CONNECTING_DBUS,
                            self._starting_kickoff_transition),
                "UPDATE": (ContextState.STARTING,
                           self._start_update_transition),
                "STOP": (ContextState.STOPPING,
                         lambda y: ContextEvent("EXIT",
                                                ExitCode.GRACEFUL_STOP))
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
            ContextState.STOPPING: {
                "EXIT": (ContextState.STOPPING,
                         self._exit_transition)
            },
            ContextState.WAITING_FOR_START_JOB: {
                "START_OK": (ContextState.POLLING,
                             self._job_finished_success_transition),
                "START_FAILURE": (ContextState.STOPPING,
                                  self._exit_transition),
                "UPDATE": (ContextState.WAITING_FOR_START_JOB,
                           self._job_update_transition),
                "STOP": (ContextState.WAITING_TO_SUBMIT_STOP_JOB,
                         lambda y: None)
            },
            ContextState.WAITING_TO_SUBMIT_STOP_JOB: {
                "START_OK": (ContextState.SUBMITTING_STOP_JOB,
                             self._waiting_to_submit_success_transition),
                "START_FAIL": (ContextState.STOPPING,
                               lambda y: ExitCode.SERVICE_FAILURE),
                "STOP": (ContextState.WAITING_TO_SUBMIT_STOP_JOB,
                         lambda y: None),
                "UPDATE": (ContextState.WAITING_TO_SUBMIT_STOP_JOB,
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
                           self._polling_update_transition),
                "STOP": (ContextState.REVERTING_RESOLV_CONF,
                         self._running_stop_transition)
            },
            ContextState.SETTING_UP_RESOLVCONF: {
                "FAIL": (ContextState.STOPPING,
                         self._exit_transition),
                "SUCCESS": (ContextState.UPDATING_RESOLV_CONF,
                            self._setting_up_resolve_conf_transition)
            },
            ContextState.RUNNING: {
                "UPDATE": (ContextState.UPDATING_RESOLV_CONF,
                           self._running_update_transition),
                "STOP": (ContextState.REVERTING_RESOLV_CONF,
                         self._running_stop_transition),
                "RELOAD": (ContextState.SUBMITTING_RESTART_JOB,
                           self._running_reload_transition)
            },
            ContextState.UPDATING_RESOLV_CONF: {
                "FAIL": (ContextState.SUBMITTING_STOP_JOB,
                         self._updating_resolv_conf_fail_transition),
                "SUCCESS": (ContextState.UPDATING_DNS_MANAGER,
                            self._updating_resolv_conf_success_transition)
            },
            ContextState.UPDATING_DNS_MANAGER: {
                "FAIL": (ContextState.REVERTING_RESOLV_CONF,
                         self.updating_dns_manager_fail_transition),
                "SUCCESS": (ContextState.RUNNING, lambda y: None)
            },
            ContextState.SUBMITTING_STOP_JOB: {
                "SUCCESS": (ContextState.WAITING_STOP_JOB, lambda y: None),
                "FAIL": (ContextState.STOPPING,
                         lambda y: ContextEvent("EXIT",
                                                ExitCode.DBUS_FAILURE))
            },
            ContextState.WAITING_STOP_JOB: {
                "STOP_SUCCESS": (ContextState.STOPPING,
                                 self._waiting_stop_job_success_transition),
                "STOP_FAILURE": (ContextState.STOPPING,
                                 self._waiting_stop_job_fail_transition),
                "STOP": (ContextState.WAITING_STOP_JOB, lambda y: None),
                "UPDATE": (ContextState.WAITING_STOP_JOB, lambda y: None)
            },
            ContextState.REVERTING_RESOLV_CONF: {
                "SUCCESS": (ContextState.SUBMITTING_STOP_JOB,
                            self._reverting_resolv_conf_transition),
                "FAIL": (ContextState.SUBMITTING_STOP_JOB,
                         self._reverting_resolv_conf_transition)
            },
            ContextState.SUBMITTING_RESTART_JOB: {
                "SUCCESS": (ContextState.WAITING_RESTART_JOB,
                            lambda y: None),
                "FAIL": (ContextState.REVERT_RESOLV_ON_FAILED_RESTART,
                         self._submitting_restart_job_fail_transition)
            },
            ContextState.REVERT_RESOLV_ON_FAILED_RESTART: {
                "SUCCESS": (ContextState.STOPPING, self._exit_transition),
                "FAIL": (ContextState.STOPPING, self._exit_transition)
            },
            ContextState.WAITING_RESTART_JOB: {
                "RESTART_SUCCESS": (ContextState.POLLING,
                                    self._job_finished_success_transition),
                "RESTART_FAIL": (ContextState.REVERT_RESOLV_ON_FAILED_RESTART,
                                 self._waiting_restart_job_failure_transition)
            }
        }

    def transition_function(self, event: ContextEvent) -> bool:
        """ Perform transition based on current state and incoming event

        :param event: Incoming event
        :type event: ContextEvent
        :return: Always false. This allows use in loop callbacks
        """
        lgr.debug(("FSM transition function called, "
                   + f"state: {self.state}, event: {event.name}"))
        try:
            while event is not None:
                self.state, callback \
                    = self.transition[self.state][event.name]
                event = callback(event)
                lgr.debug((f"New state: {self.state}, new event: " +
                           f"{event.name if event is not None else 'None'}"))
        except KeyError:
            lgr.warning((f"There is no transition defined from {self.state} "
                         + f"on {event.name} event, ignoring"))
        # a bit of a hack, so loop add functions remove this immediately
        return False

    def _starting_kickoff_transition(self, event: ContextEvent)\
            -> ContextEvent | None:
        """ Transition to CONNECTING_DBUS

        Attempt to connect to DBUS and subscribe to systemd signals

        :param event: not used
        :type event: ContextEvent
        :return: Success or FAIL with exit code
        :rtype: ContextEvent | None
        """
        if (not self._connect_systemd()
                or not self._subscribe_systemd_signals()):
            lgr.error("Failed to connect to systemd through DBUS")
            return ContextEvent("FAIL", ExitCode.DBUS_FAILURE)
        else:
            lgr.debug("Successfully connected to systemd through DBUS")
            return ContextEvent("SUCCESS")

    def _connecting_dbus_success_transition(self, event: ContextEvent)\
            -> ContextEvent | None:
        """ Transition to SUBMITTING_START_JOB

        Attempt to connect to submit systemd start job of cache service

        :param event: not used
        :type event: ContextEvent
        :return: Success or FAIL with exit code
        :rtype: ContextEvent | None
        """
        # TODO we will configure this in network_objects
        self.dns_mgr = UnboundManager()
        self.dns_mgr.configure(self.my_address)
        service_start_job = self._start_unit()
        if service_start_job is None:
            lgr.error("Failed to submit dns cache service start job")
            return ContextEvent("FAIL", ExitCode.DBUS_FAILURE)
        self._systemd_jobs[service_start_job] = (
            ContextEvent("START_OK"), ContextEvent("START_FAIL",
                                                   ExitCode.SERVICE_FAILURE))
        # end of part that will be configured
        lgr.debug("Successfully submitted dns cache service start job")
        return ContextEvent("SUCCESS")

    def _exit_transition(self, event: ContextEvent) -> ContextEvent | None:
        """ Transition to STOPPING

        Save exit code and stop main loop

        :param event: Event holding exit code in data
        :type event: ContextEvent
        :return: None
        :rtype: ContextEvent | None
        """
        lgr.debug("Stopping event loop and FSM")
        self._exit_code = event.data.value
        self._main_loop.quit()
        return None

    def _subscribe_systemd_signals(self):
        try:
            interface = dbus.Interface(self._systemd_object,
                                       "org.freedesktop.systemd1.Manager")
            interface.Subscribe()
            interface.connect_to_signal("JobRemoved",
                                        self._on_systemd_job_finished)
            return True
        except dbus.DBusException as e:
            lgr.error("Systemd is not listening on " +
                      f"name org.freedesktop.systemd1 {e}")
        return False

    def _connect_systemd(self):
        try:
            bus = dbus.SystemBus()
            self._systemd_object = bus.get_object('org.freedesktop.systemd1',
                                                  '/org/freedesktop/systemd1')
            return True
        except dbus.DBusException as e:
            lgr.error("Systemd is not listening on name "
                      + f"org.freedesktop.systemd1: {e}")
        return False

    def _on_systemd_job_finished(self, *args):
        jobid = int(args[0])
        success_event, failure_event = self._systemd_jobs.pop(jobid,
                                                              (None, None))
        if success_event is not None:
            lgr.debug(f"{args[2]} start job finished")
            if len(self._systemd_jobs.keys()) == 0:
                lgr.debug("Not waiting for more jobs, thus unsubscribing")
                # we do not want to receive info about jobs anymore
                interface = dbus.Interface(self._systemd_object,
                                           "org.freedesktop.systemd1.Manager")
                interface.Unsubscribe()
            if args[3] != "done" and args[3] != "skipped":
                lgr.error(f"{args[2]} unit failed to start, result: {args[3]}")
                self.transition_function(failure_event)
            self.transition_function(success_event)
        else:
            lgr.debug(("Dnsconfd was informed about finish of"
                       + f" job {jobid} but it was not submitted by us"))

    def _job_finished_success_transition(self, event: ContextEvent)\
            -> ContextEvent | None:
        """ Transition to POLLING

        Register timeout callback with TIMER_UP event into the main loop

        :param event: Not used
        :type event: ContextEvent
        :return: None
        :rtype: ContextEvent | None
        """
        lgr.debug("Start job finished successfully, starting polling")
        timer_event = ContextEvent("TIMER_UP", 0)
        GLib.timeout_add_seconds(1,
                                 lambda: self.transition_function(timer_event))
        return None

    def _polling_timer_up_transition(self, event: ContextEvent)\
            -> ContextEvent | None:
        """ Transition to POLLING

        Check whether service is already running and if not then whether
        Dnsconfd is waiting too long already.

        :param event: Event with count of done polls in data
        :type event: ContextEvent
        :return: None or SERVICE_UP if service is up
        :rtype: ContextEvent | None
        """
        if not self.dns_mgr.is_ready():
            if event.data == 3:
                lgr.error(f"{self.dns_mgr.service_name} did not respond in "
                          + "time, stopping dnsconfd")
                return ContextEvent("TIMEOUT", ExitCode.SERVICE_FAILURE)
            lgr.debug(f"{self.dns_mgr.service_name} still not ready, "
                      + "scheduling additional poll")
            timer = ContextEvent("TIMER_UP", event.data + 1)
            GLib.timeout_add_seconds(1,
                                     lambda: self.transition_function(timer))
            return None
        else:
            lgr.debug("DNS cache service is responding, "
                      + "proceeding to setup of resolv.conf")
            return ContextEvent("SERVICE_UP")

    def _polling_service_up_transition(self, event: ContextEvent)\
            -> ContextEvent | None:
        """ Transition to SETTING_UP_RESOLVCONF

        Attempt to set up resolv.conf

        :param event: Not used
        :type event: ContextEvent
        :return: SUCCESS if setting up was successful otherwise FAIL
        :rtype: ContextEvent | None
        """
        if not self.sys_mgr.set_resolvconf():
            lgr.error("Failed to set up resolv.conf")
            return ContextEvent("FAIL", ExitCode.RESOLV_CONF_FAILURE)
        else:
            lgr.debug("Resolv.conf successfully prepared")
            return ContextEvent("SUCCESS")

    def _running_update_transition(self, event: ContextEvent)\
            -> ContextEvent | None:
        """ Transition to UPDATING_RESOLV_CONF

        Attempt to update resolv.conf

        :param event: event with interface config in data
        :type event: ContextEvent
        :return: SUCCESS if update was successful otherwise FAIL
        :rtype: ContextEvent | None
        """
        interface_config: InterfaceConfiguration = event.data
        self.interfaces[interface_config.interface_index] = interface_config
        zones_to_servers, search_domains = self._get_zones_to_servers()
        if not self.sys_mgr.update_resolvconf(search_domains):
            return ContextEvent("FAIL", ExitCode.SERVICE_FAILURE)
        return ContextEvent("SUCCESS", zones_to_servers)

    def _updating_resolv_conf_success_transition(self, event: ContextEvent)\
            -> ContextEvent | None:
        """ Transition to UPDATING_DNS_MANAGER

        Attempt to update dns caching service with new network_objects

        :param event: event with interface config in data
        :type event: ContextEvent
        :return: SUCCESS if update was successful otherwise FAIL
        :rtype: ContextEvent | None
        """
        new_zones_to_servers = event.data
        if not self.dns_mgr.update(new_zones_to_servers):
            return ContextEvent("FAIL", ExitCode.SERVICE_FAILURE)
        return ContextEvent("SUCCESS")

    def _job_update_transition(self, event: ContextEvent)\
            -> ContextEvent | None:
        """ Transition to WAITING_FOR_START_JOB

        Save received network_objects and further wait for the start job

        :param event: event with interface config in data
        :type event: ContextEvent
        :return: None
        :rtype: ContextEvent | None
        """
        interface_config: InterfaceConfiguration = event.data
        self.interfaces[interface_config.interface_index] = interface_config
        return None

    def _waiting_to_submit_success_transition(self, event: ContextEvent)\
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
        service_stop_job = self._stop_unit()
        if service_stop_job is None:
            return ContextEvent("FAIL", ExitCode.DBUS_FAILURE)
        self._systemd_jobs[service_stop_job] = (
            ContextEvent("STOP_SUCCESS", ExitCode.GRACEFUL_STOP),
            ContextEvent("STOP_FAILURE", ExitCode.SERVICE_FAILURE))
        return ContextEvent("SUCCESS", ExitCode.GRACEFUL_STOP)

    def _polling_update_transition(self, event: ContextEvent)\
            -> ContextEvent | None:
        """ Transition to POLLING

        Save received network_objects and continue polling

        :param event: event with interface config in data
        :type event: ContextEvent
        :return: None
        :rtype: ContextEvent | None
        """
        interface_config: InterfaceConfiguration = event.data
        self.interfaces[interface_config.interface_index] = interface_config
        return None

    def _updating_resolv_conf_fail_transition(self, event: ContextEvent)\
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
        self.sys_mgr.revert_resolvconf()
        if not self._subscribe_systemd_signals():
            return ContextEvent("FAIL", ExitCode.DBUS_FAILURE)
        service_stop_job = self._stop_unit()
        if service_stop_job is None:
            return ContextEvent("FAIL", ExitCode.DBUS_FAILURE)
        self._systemd_jobs[service_stop_job] = (
            ContextEvent("STOP_SUCCESS", ExitCode.RESOLV_CONF_FAILURE),
            ContextEvent("STOP_FAILURE", ExitCode.SERVICE_FAILURE))
        return ContextEvent("SUCCESS", ExitCode.GRACEFUL_STOP)

    def _waiting_stop_job_success_transition(self, event: ContextEvent)\
            -> ContextEvent | None:
        """ Transition to STOPPING

        Move to STOPPING state and deliver exit code

        :param event: Event with exit code in data
        :type event: ContextEvent
        :return: EXIT event with exit code
        :rtype: ContextEvent | None
        """
        lgr.debug("Stop job after error successfully finished")
        return ContextEvent("EXIT", event.data)

    def _waiting_stop_job_fail_transition(self, event: ContextEvent)\
            -> ContextEvent | None:
        """ Transition to STOPPING

        Move to STOPPING state and deliver exit code with addition of service
        failure

        :param event: Event with exit code in data
        :type event: ContextEvent
        :return: EXIT event with exit code + service failure
        :rtype: ContextEvent | None
        """
        lgr.debug("Stop job after error failed")
        return ContextEvent("EXIT", ExitCode.SERVICE_FAILURE)

    def updating_dns_manager_fail_transition(self, event: ContextEvent)\
            -> ContextEvent | None:
        """ Transition to REVERTING_RESOLV_CONF

        Attempt to revert resolv.conf content

        :param event: Not used
        :type event: ContextEvent
        :return: SUCCESS or FAIL with exit code
        :rtype: ContextEvent | None
        """
        lgr.error("Failed to update DNS service, stopping")
        if not self.sys_mgr.revert_resolvconf():
            return ContextEvent("FAIL", ExitCode.RESOLV_CONF_FAILURE)
        return ContextEvent("SUCCESS", ExitCode.GRACEFUL_STOP)

    def _reverting_resolv_conf_transition(self, event: ContextEvent)\
            -> ContextEvent | None:
        """ Transition to SUBMITTING_STOP_JOB

        Attempt to submit stop job

        :param event: Event with exit code in data
        :type event: ContextEvent
        :return: SUCCESS or FAIL with exit code
        :rtype: ContextEvent | None
        """
        if not self._subscribe_systemd_signals():
            return ContextEvent("FAIL", ExitCode.DBUS_FAILURE)
        service_stop_job = self._stop_unit()
        if service_stop_job is None:
            return ContextEvent("FAIL", ExitCode.DBUS_FAILURE)
        self._systemd_jobs[service_stop_job] = (
            ContextEvent("STOP_SUCCESS", ExitCode.GRACEFUL_STOP),
            ContextEvent("STOP_FAILURE", ExitCode.SERVICE_FAILURE))
        return ContextEvent("SUCCESS", ExitCode.GRACEFUL_STOP)

    def _running_stop_transition(self, event: ContextEvent)\
            -> ContextEvent | None:
        """ Transition to REVERTING_RESOLV_CONF

        Attempt to revert resolv.conf content

        :param event: Not used
        :type event: ContextEvent
        :return: SUCCESS or FAIL with exit code
        :rtype: ContextEvent | None
        """
        lgr.info("Stopping dnsconfd")
        if not self.sys_mgr.revert_resolvconf():
            return ContextEvent("FAIL", ExitCode.RESOLV_CONF_FAILURE)
        return ContextEvent("SUCCESS", ExitCode.GRACEFUL_STOP)

    def _running_reload_transition(self, event: ContextEvent)\
            -> ContextEvent | None:
        """ Transition to SUBMITTING_RESTART_JOB

        Attempt to submit restart job

        :param event: Not used
        :type event: ContextEvent
        :return: SUCCESS or FAIL with exit code
        :rtype: ContextEvent | None
        """
        lgr.info("Reloading DNS cache service")
        self.dns_mgr.clear_state()
        if not self._subscribe_systemd_signals():
            return ContextEvent("FAIL", ExitCode.DBUS_FAILURE)
        service_restart_job = self._restart_unit()
        if service_restart_job is None:
            return ContextEvent("FAIL", ExitCode.DBUS_FAILURE)
        self._systemd_jobs[service_restart_job] = (
            ContextEvent("RESTART_SUCCESS"),
            ContextEvent("RESTART_FAIL", ExitCode.SERVICE_FAILURE))
        return ContextEvent("SUCCESS", ExitCode.GRACEFUL_STOP)

    def _setting_up_resolve_conf_transition(self, event: ContextEvent)\
            -> ContextEvent | None:
        """ Transition to SUBMITTING_RESTART_JOB

        Attempt to update resolv.conf

        :param event: Not used
        :type event: ContextEvent
        :return: SUCCESS with new zones to servers or FAIL with exit code
        :rtype: ContextEvent | None
        """
        zones_to_servers, search_domains = self._get_zones_to_servers()
        if not self.sys_mgr.update_resolvconf(search_domains):
            lgr.error("Failed to update resolv.conf")
            return ContextEvent("FAIL", ExitCode.SERVICE_FAILURE)
        lgr.debug("Successfully updated resolv.conf with search domains:"
                  + f"{search_domains}")
        return ContextEvent("SUCCESS", zones_to_servers)

    def _submitting_restart_job_fail_transition(self, event: ContextEvent)\
            -> ContextEvent | None:
        """ Transition to REVERTING_RESOLV_ON_FAILED_RESTART

        Attempt to revert resolv.conf

        :param event: Event with exit code in data
        :type event: ContextEvent
        :return: SUCCESS or FAIL with exit code
        :rtype: ContextEvent | None
        """
        if not self.sys_mgr.revert_resolvconf():
            lgr.error("Failed to revert resolv.conf")
            return ContextEvent("FAIL", ExitCode.RESOLV_CONF_FAILURE)
        lgr.debug("Successfully reverted resolv.conf")
        return ContextEvent("SUCCESS", event.data)

    def _waiting_restart_job_failure_transition(self, event: ContextEvent)\
            -> ContextEvent | None:
        """ Transition to REVERTING_RESOLV_ON_FAILED_RESTART

        Attempt to revert resolv.conf

        :param event: Not used
        :type event: ContextEvent
        :return: SUCCESS or FAIL with exit code
        :rtype: ContextEvent | None
        """
        if not self.sys_mgr.revert_resolvconf():
            lgr.error("Failed to revert resolv.conf")
            return ContextEvent("FAIL", ExitCode.SERVICE_FAILURE)
        lgr.debug("Successfully reverted resolv.conf")
        return ContextEvent("SUCCESS", ExitCode.SERVICE_FAILURE)

    def _start_update_transition(self, event: ContextEvent)\
            -> ContextEvent | None:
        """ Transition to STARTING

        Save received network_objects and further wait for start kickoff

        :param event: event with interface config in data
        :type event: ContextEvent
        :return: None
        :rtype: ContextEvent | None
        """
        interface_config: InterfaceConfiguration = event.data
        self.interfaces[interface_config.interface_index] = interface_config
        return None

    def _start_unit(self):
        lgr.info(f"Starting {self.dns_mgr.service_name}")
        interface = dbus.Interface(self._systemd_object,
                                   "org.freedesktop.systemd1.Manager")
        try:
            name = f"{self.dns_mgr.service_name}.service"
            return int(interface.ReloadOrRestartUnit(name,
                                                     "replace").split('/')[-1])
        except dbus.DBusException as e:
            lgr.error("Was not able to call "
                      + "org.freedesktop.systemd1.Manager.ReloadOrRestartUnit"
                      + f", check your policy: {e}")
        return None

    def _stop_unit(self):
        lgr.info(f"Stopping {self.dns_mgr.service_name}")
        interface = dbus.Interface(self._systemd_object,
                                   "org.freedesktop.systemd1.Manager")
        try:
            name = f"{self.dns_mgr.service_name}.service"
            return int(interface.StopUnit(name,
                                          "replace").split('/')[-1])
        except dbus.DBusException as e:
            lgr.error("Was not able to call "
                      + "org.freedesktop.systemd1.Manager.StopUnit"
                      + f", check your policy {e}")
        return None

    def _restart_unit(self):
        lgr.info(f"Restarting {self.dns_mgr.service_name}")
        interface = dbus.Interface(self._systemd_object,
                                   "org.freedesktop.systemd1.Manager")
        try:
            name = f"{self.dns_mgr.service_name}.service"
            return int(interface.RestartUnit(name, "replace").split('/')[-1])
        except dbus.DBusException as e:
            lgr.error("Was not able to call"
                      + " org.freedesktop.systemd1.Manager.RestartUnit"
                      + f", check your policy: {e}")
        return None

    def _get_zones_to_servers(self):
        new_zones_to_servers = {}

        search_domains = []

        for interface in self.interfaces.values():
            lgr.debug(f"Processing interface {interface}")
            interface: InterfaceConfiguration
            interface_zones = []
            search_domains = []
            for dom in interface.domains:
                if dom[1]:
                    interface_zones.append(dom[0])
                else:
                    search_domains.append(dom[0])
            if interface.is_default:
                lgr.debug("Interface is default, appending . as its zone")
                interface_zones.append(".")
            for zone in interface_zones:
                lgr.debug(f"Handling zone {zone} of the interface")
                new_zones_to_servers[zone] = new_zones_to_servers.get(zone, [])
                for server in interface.servers:
                    lgr.debug(f"Handling server {server}")
                    found_server = []
                    for a in new_zones_to_servers[zone]:
                        if server == a:
                            found_server.append(a)
                    if len(found_server) > 0:
                        lgr.debug(f"Server {server} already in zone, "
                                  + "handling priority")
                        prio = max(found_server[0].priority, server.priority)
                        found_server[0].priority = prio
                    else:
                        lgr.debug(f"Appending server {server} to zone {zone}")
                        new_zones_to_servers[zone].append(server)

        for zone in new_zones_to_servers.keys():
            new_zones_to_servers[zone].sort(key=lambda x: x.priority,
                                            reverse=True)

        return new_zones_to_servers, search_domains

    def get_status(self, json_format: bool) -> str:
        """ Get current status of Dnsconfd

        :param json_format: True if status should be in JSON format
        :return: String with status
        :rtype: str
        """
        lgr.debug("Handling request for status")
        interfaces = self.interfaces.values()
        if json_format:
            status = {"service": self.dns_mgr.service_name,
                      "cache_config": self.dns_mgr.get_status(),
                      "state": self.state.name,
                      "interfaces": [a.to_dict() for a in interfaces]}
            return json.dumps(status)
        return (f"Running cache service:\n{self.dns_mgr.service_name}\n"
                + "Config present in service:\n"
                + f"{json.dumps(self.dns_mgr.get_status(), indent=4)}\n"
                + f"State of Dnsconfd:\n{self.state.name}\n"
                + "Info about interfaces: "
                + f"{json.dumps([a.to_dict() for a in interfaces], indent=4)}")

    def reload_service(self) -> str:
        """ Perform reload of cache service if possible

        :return: String with answer
        :rtype: str
        """
        if self.state != ContextState.RUNNING:
            return ("Reload can not be performed at this time. "
                    + f"Current state: {self.state}")
        else:
            self.transition_function(ContextEvent("RELOAD"))
            return "Starting reload"

    def get_exit_code(self) -> int:
        """ Get exit code Dnsconfd should stop with

        :return: exit code
        :rtype: int
        """
        return self._exit_code
