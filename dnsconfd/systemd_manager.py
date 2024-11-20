import logging
from typing import Callable, Optional
import dbus

from dnsconfd.fsm import ContextEvent


class SystemdManager:
    def __init__(self, transition_function: Callable):
        """ Manager of systemd operations

        :param transition_function: function to be called when transition is
        necessary
        """
        self.systemd_interface = None
        self._signal_connection = None
        self.lgr = logging.getLogger(self.__class__.__name__)
        self.transition_function = transition_function
        self.systemd_jobs: dict[int, tuple[ContextEvent, ContextEvent]] = {}

    def subscribe_systemd_signals(self):
        """ Subscribe to JobRemoved systemd signal

        :return: True on success, otherwise False
        """
        try:
            self.systemd_interface.Subscribe()
            connection = (self.systemd_interface.
                          connect_to_signal("JobRemoved",
                                            self._on_systemd_job_finished))
            self._signal_connection = connection
            return True
        except dbus.DBusException as e:
            self.lgr.error("Systemd is not listening on "
                           "name org.freedesktop.systemd1", e)
        return False

    def _on_systemd_job_finished(self, *args):
        jobid = int(args[0])
        success_event, failure_event = self.systemd_jobs.pop(jobid,
                                                             (None, None))
        if success_event is not None:
            self.lgr.debug("%s start job finished", args[2])
            if not self.systemd_jobs:
                self.lgr.debug("Not waiting for more jobs, unsubscribing")
                # we do not want to receive info about jobs anymore
                self.systemd_interface.Unsubscribe()
                self._signal_connection.remove()
            if args[3] != "done" and args[3] != "skipped":
                self.lgr.error("%s unit failed to start, "
                               "result: %s", args[2], args[3])
                self.transition_function(failure_event)
            self.transition_function(success_event)
        else:
            self.lgr.debug("Dnsconfd was informed about finish of "
                           "job %s but it was not submitted by us", jobid)

    def change_unit_state(self,
                          new_state: int,
                          unit: str,
                          success_event: ContextEvent,
                          failure_event: ContextEvent) -> Optional[int]:
        """ Change state of systemd unit

        :param new_state: integer indicating what state should be set
        0 - start 1 - restart 2 - stop
        :param unit: name of the unit
        :param success_event: Event that should be pushed on success
        :param failure_event: Event that should be pushed on failure
        :return: job id on success otherwise None
        """
        self.lgr.info("%s %s",
                      ["Starting", "Restarting", "Stopping"][new_state], unit)
        try:
            name = f"{unit}.service"
            if new_state == 0:
                result = self.systemd_interface.ReloadOrRestartUnit(name,
                                                                    "replace")
            elif new_state == 1:
                result = self.systemd_interface.RestartUnit(name, "replace")
            else:
                result = self.systemd_interface.StopUnit(name, "replace")
            jobid = int(result.split('/')[-1])
        except dbus.DBusException as e:
            self.lgr.error("Was not able to call "
                           "change state of systemd unit"
                           ", check your policy: %s", e)
            return None
        self.systemd_jobs[jobid] = (success_event, failure_event)
        return jobid

    def connect_systemd(self):
        """ Connect to Systemd DBUS interface

        :return: True on success, otherwise False
        """
        try:
            systemd_object = dbus.SystemBus().get_object(
                'org.freedesktop.systemd1',
                '/org/freedesktop/systemd1')
            self.systemd_interface \
                = dbus.Interface(systemd_object,
                                 "org.freedesktop.systemd1.Manager")
            return True
        except dbus.DBusException as e:
            self.lgr.error("Systemd is not listening on name "
                           "org.freedesktop.systemd1: %s", e)
        return False
