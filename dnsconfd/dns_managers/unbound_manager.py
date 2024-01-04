from dnsconfd.dns_managers.dns_manager import DnsManager
from dnsconfd.configuration import ServerDescription

import subprocess
import tempfile
import shutil
import logging as lgr


class UnboundManager(DnsManager):
    service_name = "unbound"
    systemctl = "systemctl"

    def __init__(self):
        self.temp_dir_path = None
        self.process = None
        self.zones_to_servers = {}
        self.validation = False

    def configure(self, my_address, validation = False):
        if self.temp_dir_path is None:
            self.temp_dir_path = tempfile.mkdtemp()
        self.my_address = my_address
        self.validation = validation
        lgr.debug(f"DNS cache should be listening on {self.my_address}")

    def start(self):
        lgr.info(f"Starting {self.service_name}")
        self._execute_systemctl("start", [self.service_name])

    def stop(self):
        lgr.info(f"Stoping {self.service_name}")
        self._execute_systemctl("stop", [self.service_name])

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

    # TODO: move out to common classes
    def _execute_systemctl(self, command: str, args: list):
        control_args = [self.systemctl, command]
        control_args.extend(args)
        lgr.debug(f"Executing systemctl as {' '.join(control_args)}")
        proc = subprocess.run(control_args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        lgr.debug(f"Returned code {proc.returncode}, stdout:\"{proc.stdout}\", stderr:\"{proc.stderr}\"")
        return proc.returncode

    def update(self, new_zones_to_servers: dict[list[ServerDescription]]):
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
