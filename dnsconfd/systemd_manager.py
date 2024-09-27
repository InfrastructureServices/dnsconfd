import logging
from typing import Callable

import dbus

from dnsconfd.fsm import ContextEvent


class SystemdManager:
    def __init__(self, transition_function: Callable):
        self.systemd_interface = None
        self._signal_connection = None
        self.lgr = logging.getLogger(self.__class__.__name__)
        self.transition_function = transition_function
        self.systemd_jobs: dict[int, tuple[ContextEvent, ContextEvent]] = {}

    def subscribe_systemd_signals(self):
        try:
            self.systemd_interface.Subscribe()
            connection = (self.systemd_interface.
                          connect_to_signal("JobRemoved",
                                            self.on_systemd_job_finished))
            self._signal_connection = connection
            return True
        except dbus.DBusException as e:
            self.lgr.error("Systemd is not listening on " +
                           f"name org.freedesktop.systemd1 {e}")
        return False

    def on_systemd_job_finished(self, *args):
        jobid = int(args[0])
        success_event, failure_event = self.systemd_jobs.pop(jobid,
                                                             (None, None))
        if success_event is not None:
            self.lgr.debug(f"{args[2]} start job finished")
            if not self.systemd_jobs:
                self.lgr.debug("Not waiting for more jobs, thus unsubscribing")
                # we do not want to receive info about jobs anymore
                self.systemd_interface.Unsubscribe()
                self._signal_connection.remove()
            if args[3] != "done" and args[3] != "skipped":
                self.lgr.error(f"{args[2]} unit failed to start, "
                               f"result: {args[3]}")
                self.transition_function(failure_event)
            self.transition_function(success_event)
        else:
            self.lgr.debug("Dnsconfd was informed about finish of"
                           f" job {jobid} but it was not submitted by us")

    def restart_unit(self,
                     unit: str,
                     success_event: ContextEvent,
                     failure_event: ContextEvent):
        self.lgr.info(f"Restarting {unit}")
        try:
            name = f"{unit}.service"
            jobid = int(self.systemd_interface
                        .RestartUnit(name, "replace").split('/')[-1])
        except dbus.DBusException as e:
            self.lgr.error("Was not able to call "
                           "org.freedesktop.systemd1.Manager.RestartUnit"
                           f", check your policy: {e}")
            return None
        self.systemd_jobs[jobid] = (success_event, failure_event)
        return jobid

    def connect_systemd(self):
        try:
            systemd_object = dbus.SystemBus().get_object('org.freedesktop.systemd1',
                                                         '/org/freedesktop/systemd1')
            self.systemd_interface \
                = dbus.Interface(systemd_object,
                                 "org.freedesktop.systemd1.Manager")
            return True
        except dbus.DBusException as e:
            self.lgr.error("Systemd is not listening on name "
                           f"org.freedesktop.systemd1: {e}")
        return False

    def start_unit(self,
                   unit: str,
                   success_event: ContextEvent,
                   failure_event: ContextEvent):
        self.lgr.info(f"Starting {unit}")
        try:
            name = f"{unit}.service"
            jobid = int(self.systemd_interface
                        .ReloadOrRestartUnit(name,
                                             "replace").split('/')[-1])
        except dbus.DBusException as e:
            self.lgr.error("Was not able to call "
                           "org.freedesktop.systemd1.Manager"
                           f".ReloadOrRestartUnit , check your policy: {e}")
            return None
        self.systemd_jobs[jobid] = (success_event, failure_event)
        return jobid

    def stop_unit(self,
                  unit: str,
                  success_event: ContextEvent,
                  failure_event: ContextEvent):
        self.lgr.info(f"Stopping {unit}")
        try:
            name = f"{unit}.service"
            jobid = int(self.systemd_interface
                        .StopUnit(name,
                                  "replace").split('/')[-1])
        except dbus.DBusException as e:
            self.lgr.error("Was not able to call "
                           "org.freedesktop.systemd1.Manager.StopUnit"
                           f", check your policy {e}")
            return None
        self.systemd_jobs[jobid] = (success_event, failure_event)
        return jobid
