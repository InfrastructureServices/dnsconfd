from dnsconfd.dns_managers.dns_manager import DnsManager
from dnsconfd.configuration import ServerDescription

import subprocess
import tempfile
import logging as lgr
import dbus
import copy
import time

class UnboundManager(DnsManager):
    service_name = "unbound"
    systemctl = "systemctl"

    def __init__(self):
        self.temp_dir_path = None
        self.process = None
        self.zones_to_servers = {}
        self.validation = False
        self._systemd_object = None
        self._service_start_job = None
        self._started = False
        self._buffer = None

    def configure(self, my_address, validation = False):
        if self.temp_dir_path is None:
            self.temp_dir_path = tempfile.mkdtemp()
        self.my_address = my_address
        self.validation = validation
        lgr.debug(f"DNS cache should be listening on {self.my_address}")

    def _connect_systemd(self):
        try:
            self._systemd_object = dbus.SystemBus().get_object('org.freedesktop.systemd1',
                                                    '/org/freedesktop/systemd1')
            return True
        except dbus.DBusException as e:
            lgr.error("Systemd is not listening on name org.freedesktop.systemd1")
            lgr.error(str(e))
        return False

    def _service_start_finished(self, *args):
        if self._service_start_job is not None and int(args[0]) == self._service_start_job:
            lgr.debug("Unbound start job finished")
            self._started = True
            # we do not want to receive info about jobs anymore
            self._get_systemd_interface("org.freedesktop.systemd1.Manager").Unsubscribe()
            # better way to find out whether unbound is ready was not found
            while self._execute_cmd("status") != 0:
                lgr.debug("Start job finished but unbound still not ready, waiting")
                time.sleep(1)
            if self._buffer:
                lgr.debug("Found derefered update, pushing to unbound now")
                self.update(self._buffer)
                self._buffer = None

    def _subscribe_systemd_signals(self):
        interface = self._get_systemd_interface("org.freedesktop.systemd1.Manager")
        interface.Subscribe()
        interface.connect_to_signal("JobRemoved", self._service_start_finished)

    def _get_systemd_interface(self, interface: str) -> dbus.Interface:
        try:
            return dbus.Interface(self._systemd_object, interface)
        except dbus.DBusException as e:
            lgr.error(f"Was not able to acquire {interface} interface")
            lgr.error(str(e))
        return None

    def start(self):
        lgr.info(f"Starting {self.service_name}")
        if not self._connect_systemd():
            return False
        self._subscribe_systemd_signals()
        try:
            interface = self._get_systemd_interface("org.freedesktop.systemd1.Manager")
            self._service_start_job = interface.ReloadOrRestartUnit(f"{self.service_name}.service",
                                                                    "replace").split('/')[-1]
            self._service_start_job = int(self._service_start_job)
            return True
        except dbus.DBusException as e:
            lgr.error("Was not able to call org.freedesktop.systemd1.Manager.ReloadOrRestartUnit"
                      + ", check your policy")
            lgr.error(str(e))
        return False
        # start or restart unbound service

    def stop(self):
        lgr.info(f"Stoping {self.service_name}")
        try:
            interface = self._get_systemd_interface("org.freedesktop.systemd1.Manager")
            interface.StopUnit(f"{self.service_name}.service", "replace")
            return True
        except dbus.DBusException as e:
            lgr.error("Was not able to call org.freedesktop.systemd1.Manager.StopUnit"
                      + ", check your policy")
            lgr.error(str(e))
        return False
        # stop unbound service

    def clean(self):
        # FIXME: remove
        lgr.debug("Performing cleanup after unbound")
        self.temp_dir_path = None

    def _execute_cmd(self, command: str):
        control_args = ["unbound-control", f'{command}']
        lgr.debug(f"Executing unbound-control as {' '.join(control_args)}")
        proc = subprocess.run(control_args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        lgr.debug(f"Returned code {proc.returncode}, stdout:\"{proc.stdout}\", stderr:\"{proc.stderr}\"")
        return proc.returncode

    def update(self, new_zones_to_servers: dict[list[ServerDescription]]):
        if self._started == False:
            # deep copy is needed, because otherwise we could touch referenced dict from
            # context manager in inconsistent state
            self._buffer = copy.deepcopy(new_zones_to_servers)
            lgr.debug("Unbound manager tried to process update but unbound is not running,"
                      + " derefering")
            return
        lgr.debug("Unbound manager processing update")
        insecure = "+i"
        if self.validation:
            insecure = ""

        added_zones = [zone for zone in new_zones_to_servers.keys() if zone not in self.zones_to_servers.keys()]
        removed_zones = [zone for zone in self.zones_to_servers.keys() if zone not in new_zones_to_servers.keys()]
        stable_zones = [zone for zone in new_zones_to_servers.keys() if zone in self.zones_to_servers.keys()]

        lgr.debug(f"Update added zones {added_zones}")
        lgr.debug(f"Update removed zones {removed_zones}")
        lgr.debug(f"Zones that were in both configurations {stable_zones}")

        # NOTE: unbound does not support forwarding server priority, so we need to strip any server
        # that has lower priority than the highest occured priority
        # TODO: This has to be documented
        for zone in removed_zones:
            self._execute_cmd(f"forward_remove {zone}")
        for zone in added_zones:
            servers_strings = [srv.to_unbound_string() for srv in new_zones_to_servers[zone] if srv.priority == new_zones_to_servers[zone][0].priority]
            self._execute_cmd(f"forward_add {insecure} {zone} {' '.join(servers_strings)}")
        for zone in stable_zones:
            if (self.zones_to_servers[zone] == new_zones_to_servers[zone]):
                lgr.debug(f"Zone {zone} is the same in old and new config thus skipping it")
                continue
            lgr.debug(f"Updating zone {zone}")
            self._execute_cmd(f"forward_remove {zone}")
            servers_strings = [srv.to_unbound_string() for srv in new_zones_to_servers[zone] if srv.priority == new_zones_to_servers[zone][0].priority]
            self._execute_cmd(f"forward_add {insecure} {zone} {' '.join(servers_strings)}")

        self.zones_to_servers = new_zones_to_servers
        lgr.info(f"Unbound updated to configuration: {self.get_status()}")

    def get_status(self):
        status={}
        for zone, servers in self.zones_to_servers.items():
            status[zone] = [str(srv) for srv in servers]
        return status
