import subprocess
import logging
from copy import deepcopy

from dnsconfd.dns_managers import DnsManager
from dnsconfd.network_objects import ServerDescription, DnsProtocol


class UnboundManager(DnsManager):
    service_name = "unbound"

    def __init__(self, dnssec: bool):
        """ Object responsible for executing unbound configuration changes
        :param dnssec: Indicating whether dnssec should be enabled
        """
        super().__init__()
        self.zones_to_servers = {}
        self.lgr = logging.getLogger(self.__class__.__name__)
        self.dnssec = dnssec

    def configure(self, my_address: str) -> bool:
        """ Configure this instance (Write to unbound config file)

        :param my_address: address where unbound should listen
        :type my_address: str
        :return: True on success, otherwise False
        :rtype: bool
        """
        if self.dnssec:
            modules = "ipsecmod validator iterator"
        else:
            modules = "ipsecmod iterator"
        try:
            with open("/run/dnsconfd/unbound.conf", "w",
                      encoding="utf-8") as conf_file:
                conf_file.write("server:\n"
                                f"\tmodule-config: \"{modules}\"\n"
                                f"\tinterface: {my_address}\n"
                                f"\tdo-not-query-address: 127.0.0.1/8\n"
                                "forward-zone:\n"
                                "\tname: \".\"\n"
                                "\tforward-addr: \"127.0.0.1\"\n")
        except OSError as e:
            self.lgr.critical("Could not write Unbound configuration, %s",
                              e)
            return False

        self.lgr.debug("DNS cache should be listening on %s", my_address)
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
                      "%s", ' '.join(control_args))
        proc = subprocess.run(control_args,
                              stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE,
                              check=False)
        self.lgr.debug("Returned code %s, "
                       "stdout: \"%s\", "
                       "stderr:\"%s\"",
                       proc.returncode, proc.stdout, proc.stderr)
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
        for zone in zones_to_servers:
            if zone in self.zones_to_servers:
                stable_zones.append(zone)
            else:
                added_zones.append(zone)

        for zone in self.zones_to_servers:
            if zone not in zones_to_servers:
                removed_zones.append(zone)

        self.lgr.debug("Update added zones %s", added_zones)
        self.lgr.debug("Update removed zones %s", removed_zones)
        self.lgr.debug("Zones that were in both configurations %s",
                       stable_zones)

        # NOTE: unbound does not support forwarding server priority, so we
        # need to strip any server that has lower priority than the
        # highest occurred priority
        # TODO: This has to be documented
        # NOTE: since unbound allows enabling of tls only for entire zones,
        # we will be stripping non-tls servers if tls is enabled
        # TODO: Document this
        for zone in removed_zones:
            # 127.0.0.1 works here, because unbound has 127.0.0.1/8 in
            # do-not-query-address by default, and we add that in our config
            if zone == ".":
                if (not self._execute_cmd("forward_add . 127.0.0.1")
                        or not self._execute_cmd(f"flush_zone {zone}")):
                    return False
                continue
            if (not self._execute_cmd(f"forward_remove +i {zone}")
                    or not self._execute_cmd(f"flush_zone {zone}")):
                return False
        for zone in added_zones:
            add_cmd = self._get_forward_add_command(zone,
                                                    zones_to_servers[zone])
            if (not self._execute_cmd(add_cmd)
                    or not self._execute_cmd(f"flush_zone {zone}")):
                return False
        for zone in stable_zones:
            if self.zones_to_servers[zone] == zones_to_servers[zone]:
                self.lgr.debug("Zone %s is the same in old and new "
                               "config thus skipping it", zone)
                continue
            self.lgr.debug("Updating zone %s", zone)
            add_cmd = self._get_forward_add_command(zone,
                                                    zones_to_servers[zone])
            if (not self._execute_cmd(f"forward_remove +i {zone}")
                    or not self._execute_cmd(add_cmd)
                    or not self._execute_cmd(f"flush_zone {zone}")):
                return False

        # since we need to break references to ServerDescription objects
        # held before, but keep all the metadata, deepcopy is required
        self.zones_to_servers = deepcopy(zones_to_servers)
        self.lgr.info("Unbound updated to configuration: %s",
                      self.get_status())
        return True

    def _get_forward_add_command(self,
                                 zone: str,
                                 servers: list[ServerDescription]):
        max_prio = servers[0].priority
        used_protocol = servers[0].protocol
        servers_str = []
        # this will remove duplicate servers
        unique_servers = {}
        insecure = False
        for srv in servers:
            if srv.protocol == used_protocol and srv.priority == max_prio:
                srv_string = srv.to_unbound_string()
                if srv_string not in unique_servers:
                    servers_str.append(srv_string)
                    unique_servers[srv.to_unbound_string()] = True
                if self.dnssec and not insecure and not srv.dnssec:
                    insecure = True
            else:
                break
        tls = used_protocol == DnsProtocol.DNS_OVER_TLS
        flags = None
        if tls or insecure:
            flags = f"+{'i' if insecure else ''}{'t' if tls else ''} "

        return (f"forward_add {flags if flags else ''}"
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
