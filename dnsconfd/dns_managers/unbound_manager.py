from dnsconfd.dns_managers import DnsManager
from dnsconfd.network_objects import ServerDescription, DnsProtocol

import subprocess
import logging
from copy import deepcopy


class UnboundManager(DnsManager):
    service_name = "unbound"

    def __init__(self):
        """ Object responsible for executing unbound configuration changes """
        super().__init__()
        self.zones_to_servers = {}
        self.lgr = logging.getLogger(self.__class__.__name__)

    def configure(self, my_address: str, validation=False) -> bool:
        """ Configure this instance (Write to unbound config file)

        :param my_address: address where unbound should listen
        :type my_address: str
        :param validation: enable DNSSEC validation, defaults to False
        :type validation: bool, optional
        :return: True on success, otherwise False
        :rtype: bool
        """
        if validation:
            modules = "ipsecmod validator iterator"
        else:
            modules = "ipsecmod iterator"
        try:
            with open("/run/dnsconfd/unbound.conf", "w") as conf_file:
                conf_file.writelines(["server:\n",
                                      f"\tmodule-config: \"{modules}\"\n",
                                      f"\tinterface: {my_address}\n"])
        except OSError as e:
            self.lgr.critical(f"Could not write Unbound configuration, {e}")
            return False

        self.lgr.debug(f"DNS cache should be listening on {my_address}")
        return True

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

    def _execute_cmd(self, command: str) -> bool:
        """ Execute command through unbound-control utility

        :param command: Command to execute
        :type command: str
        :return: True if command was successful, otherwise False
        :rtype: bool
        """
        control_args = ["unbound-control", f'{command}']
        self.lgr.info("Executing unbound-control as "
                      f"{' '.join(control_args)}")
        proc = subprocess.run(control_args,
                              stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE)
        self.lgr.debug(f"Returned code {proc.returncode}, "
                       f"stdout:\"{proc.stdout}\", "
                       f"stderr:\"{proc.stderr}\"")
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
        self.lgr.debug("Unbound manager processing update")

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

        self.lgr.debug(f"Update added zones {added_zones}")
        self.lgr.debug(f"Update removed zones {removed_zones}")
        self.lgr.debug("Zones that were in both configurations"
                       f" {stable_zones}")

        # NOTE: unbound does not support forwarding server priority, so we
        # need to strip any server that has lower priority than the
        # highest occurred priority
        # TODO: This has to be documented
        # NOTE: since unbound allows enabling of tls only for entire zones,
        # we will be stripping non-tls servers if tls is enabled
        # TODO: Document this
        for zone in removed_zones:
            if (not self._execute_cmd(f"forward_remove {zone}")
                    or not self._execute_cmd(f"flush_zone {zone}")):
                return False
        for zone in added_zones:
            add_cmd = self._get_forward_add_command(zone,
                                                    zones_to_servers[zone])
            if (not self._execute_cmd(f"flush_zone {zone}")
                    or not self._execute_cmd(add_cmd)):
                return False
        for zone in stable_zones:
            if self.zones_to_servers[zone] == zones_to_servers[zone]:
                self.lgr.debug(f"Zone {zone} is the same in old and new "
                               + "config thus skipping it")
                continue
            self.lgr.debug(f"Updating zone {zone}")
            add_cmd = self._get_forward_add_command(zone,
                                                    zones_to_servers[zone])
            if (not self._execute_cmd(f"forward_remove {zone}")
                    or not self._execute_cmd(f"flush_zone {zone}")
                    or not self._execute_cmd(add_cmd)):
                return False

        # since we need to break references to ServerDescription objects
        # held before, but keep all the metadata, deepcopy is required
        self.zones_to_servers = deepcopy(zones_to_servers)
        self.lgr.info(f"Unbound updated to configuration: {self.get_status()}")
        return True

    @staticmethod
    def _get_forward_add_command(zone: str,
                                 servers: list[ServerDescription]):
        max_prio = servers[0].priority
        used_protocol = servers[0].protocol
        servers_str = []
        # this will remove duplicate servers
        unique_servers = {}
        for srv in servers:
            if srv.protocol == used_protocol and srv.priority == max_prio:
                srv_string = srv.to_unbound_string()
                if srv_string not in unique_servers:
                    servers_str.append(srv_string)
                    unique_servers[srv.to_unbound_string()] = True
            else:
                break
        tls = used_protocol == DnsProtocol.DNS_OVER_TLS
        return (f"forward_add{' +t ' if tls else ' '}"
                f"{zone} {' '.join(servers_str)}")

    def get_status(self) -> dict[str, list[str]]:
        """ Get current forwarders' network_objects that this instance holds

        :return: dictionary mapping zones -> list of servers
        :rtype: dict[str, list[str]]
        """
        status = {}
        for zone, servers in self.zones_to_servers.items():
            status[zone] = [str(srv) for srv in servers]
        return status
