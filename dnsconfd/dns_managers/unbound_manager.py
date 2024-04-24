from dnsconfd.dns_managers import DnsManager
from dnsconfd.network_objects import ServerDescription

import subprocess
import logging as lgr


class UnboundManager(DnsManager):
    service_name = "unbound"

    def __init__(self):
        """ Object responsible for executing unbound network_objects changes """
        super().__init__()
        self.my_address = None
        self.zones_to_servers = {}
        self.validation = False

    def configure(self, my_address: str, validation=False):
        """ Configure this instance

        :param my_address: address where unbound should listen
        :type my_address: str
        :param validation: enable DNSSEC validation, defaults to False
        :type validation: bool, optional
        """
        self.my_address = my_address
        self.validation = validation
        lgr.debug(f"DNS cache should be listening on {self.my_address}")

    def clear_state(self):
        """ Clear state that this instance holds

            When inconsistency could not be avoided, and we need to configure
            unbound from the start, this has to be called
        """
        self.zones_to_servers = {}

    def is_ready(self) -> bool:
        """ Get whether unbound service is up and ready

        :return: True if unbound is ready to handle commands, otherwise False
        :rtype: bool
        """
        return self._execute_cmd("status")

    @staticmethod
    def _execute_cmd(command: str) -> bool:
        """ Execute command through unbound-control utility

        :param command: Command to execute
        :type command: str
        :return: True if command was successful, otherwise False
        :rtype: bool
        """
        control_args = ["unbound-control", f'{command}']
        lgr.debug(f"Executing unbound-control as {' '.join(control_args)}")
        proc = subprocess.run(control_args,
                              stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE)
        lgr.debug((f"Returned code {proc.returncode}, "
                   + f"stdout:\"{proc.stdout}\", stderr:\"{proc.stderr}\""))
        return proc.returncode == 0

    def update(self,
               zones_to_servers: dict[str, list[ServerDescription]]) -> bool:
        """ Update Unbound running service forwarders network_objects

        :param zones_to_servers: Forwarders' network_objects that should
                                 be loaded into unbound
        :type zones_to_servers: dict[str, list[ServerDescription]]
        :return: True if update was successful, otherwise False
        :rtype: bool
        """
        lgr.debug("Unbound manager processing update")
        insecure = "+i"
        if self.validation:
            insecure = ""

        added_zones = []
        stable_zones = []
        removed_zones = []
        for zone in zones_to_servers.keys():
            if zone in self.zones_to_servers.keys():
                stable_zones.append(zone)
            else:
                added_zones.append(zone)

        for zone in self.zones_to_servers.keys():
            if zone not in zones_to_servers.keys():
                removed_zones.append(zone)

        lgr.debug(f"Update added zones {added_zones}")
        lgr.debug(f"Update removed zones {removed_zones}")
        lgr.debug(f"Zones that were in both configurations {stable_zones}")

        # NOTE: unbound does not support forwarding server priority, so we
        # need to strip any server that has lower priority than the
        # highest occurred priority
        # TODO: This has to be documented
        for zone in removed_zones:
            if not self._execute_cmd(f"forward_remove {zone}"):
                return False
        for zone in added_zones:
            max_prio = zones_to_servers[zone][0].priority
            servers_str = [srv.to_unbound_string()
                           for srv in zones_to_servers[zone] if
                           srv.priority == max_prio]
            if not self._execute_cmd(f"forward_add {insecure} {zone} "
                                     + f"{' '.join(servers_str)}"):
                return False
        for zone in stable_zones:
            if self.zones_to_servers[zone] == zones_to_servers[zone]:
                lgr.debug(f"Zone {zone} is the same in old and new config "
                          + "thus skipping it")
                continue
            lgr.debug(f"Updating zone {zone}")
            max_prio = zones_to_servers[zone][0].priority
            servers_str = [srv.to_unbound_string()
                           for srv in zones_to_servers[zone] if
                           srv.priority == max_prio]
            if (not self._execute_cmd(f"forward_remove {zone}")
                    or not self._execute_cmd(f"forward_add {insecure} {zone} "
                                             + f"{' '.join(servers_str)}")):
                return False

        self.zones_to_servers = zones_to_servers
        lgr.info(f"Unbound updated to configuration: {self.get_status()}")
        return True

    def get_status(self) -> dict[str, list[str]]:
        """ Get current forwarders' network_objects that this instance holds

        :return: dictionary mapping zones -> list of servers
        :rtype: dict[str, list[str]]
        """
        status = {}
        for zone, servers in self.zones_to_servers.items():
            status[zone] = [str(srv) for srv in servers]
        return status
