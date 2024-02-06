from dnsconfd.dns_managers.dns_manager import DnsManager
from dnsconfd.configuration import ServerDescription

import subprocess
import logging as lgr

class UnboundManager(DnsManager):
    service_name = "unbound"

    def __init__(self):
        """ Object responsible for executing unbound configuration changes
        """
        # list of current forward zones and servers that running unbound service holds
        self.zones_to_servers = {}
        self.validation = False
        # startup was finished, this means service is ready to respond to controll commands
        self.start_finished = False

    def configure(self, my_address : str, validation = False):
        """ Configure this instance

        :param my_address: ddress where unbound should listen
        :type my_address: str
        :param validation: enable DNSSEC validation, defaults to False
        :type validation: bool, optional
        """
        self.my_address = my_address
        self.validation = validation
        lgr.debug(f"DNS cache should be listening on {self.my_address}")

    def clear_state(self):
        """ Clear state that this instance holds

            When inconsistency could not be avoided and we need to configure
            unbound from the start, this has to be called
        """
        # this forbids other calls from interupting next configuration process
        self.start_finished = False
        self.zones_to_servers = {}

    def is_ready(self) -> bool:
        """ Get whether unbound service is up and ready

        :return: True if unbound is ready to handle commands, otherwise False
        :rtype: bool
        """
        return self._execute_cmd("status") == 0

    def _execute_cmd(self, command: str):
        control_args = ["unbound-control", f'{command}']
        lgr.debug(f"Executing unbound-control as {' '.join(control_args)}")
        proc = subprocess.run(control_args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        lgr.debug(f"Returned code {proc.returncode}, stdout:\"{proc.stdout}\", stderr:\"{proc.stderr}\"")
        return proc.returncode

    def update(self, new_zones_to_servers: dict[list[ServerDescription]]):
        """ Update unbound running service forwarders configuration

        :param new_zones_to_servers: Forwarders' configuration that should be loaded into unbound
        :type new_zones_to_servers: dict[list[ServerDescription]]
        """
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

    def get_status(self) -> dict[str, list[str]]:
        """ Get current forwarders' configuration that this instance holds

        :return: dictionary zone -> list of servers
        :rtype: dict[str, list[str]]
        """
        status={}
        for zone, servers in self.zones_to_servers.items():
            status[zone] = [str(srv) for srv in servers]
        return status

    def flush_cache(self, domain="."):
        return self._execute_cmd("flush "+domain) == 0
