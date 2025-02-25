import subprocess
import logging
from copy import deepcopy
from typing import Optional
import os.path

from dnsconfd.dns_managers import DnsManager
from dnsconfd.network_objects import ServerDescription, DnsProtocol

try:
    import idna
    HAVE_IDNA = True
except ImportError:
    HAVE_IDNA = False


class UnboundManager(DnsManager):
    service_name = "unbound"

    def __init__(self, config: dict):
        """ Object responsible for executing unbound configuration changes
        """
        super().__init__()
        self.zones_to_servers = {}
        self.lgr = logging.getLogger(self.__class__.__name__)
        self.dnssec = config["dnssec_enabled"]
        self.address = config["listen_address"]
        self.current_ca = None
        self.default_ca: str = config["certification_authority"]
        self._configuration_serial = 1
        self._requested_configuration_serial = 1

    @property
    def configuration_serial(self):
        return self._configuration_serial

    def bump_configuration_serial(self):
        # configuration serial has to have minimal value of 1 as we will
        # return 0 on error
        if self._requested_configuration_serial < 2**32 - 2:
            self._requested_configuration_serial += 1
        else:
            self._requested_configuration_serial = 1
        return self._requested_configuration_serial

    def _get_default_ca(self):
        default_ca = self.default_ca or " ".join[
            "/etc/pki/dns/extracted/pem/tls-ca-bundle.pem",
            " /etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem",
        ]

        for entry in default_ca.split(" "):
            if os.path.isfile(entry):
                return entry

    def get_conf_string(self,
                        zones_to_servers:
                        dict[str, list[ServerDescription]] = None) -> str:
        """ Get string of Unbound configuration
        
        :param zones_to_servers: Dictionary mapping zone names to list of
                                 servers
        :return: Configuration string
        """
        if self.dnssec:
            modules = "ipsecmod validator iterator"
        else:
            modules = "ipsecmod iterator"

        if self.current_ca is None:
            ca = self._get_default_ca()
        else:
            ca = self.current_ca

        base = ("server:\n"
                f"\tmodule-config: \"{modules}\"\n"
                f"\tinterface: {self.address}\n"
                f"\tdo-not-query-address: 127.0.0.1/8\n"
                f"\ttls-cert-bundle: {ca}\n")

        if not zones_to_servers:
            return base + ("forward-zone:\n"
                           "\tname: \".\"\n"
                           "\tforward-addr: \"127.0.0.1\"\n")

        for zone in zones_to_servers:
            base += ("forward-zone:\n"
                     f"\tname: \"{zone}\"\n")
            tls = False
            for server in zones_to_servers[zone]:
                if server.protocol == DnsProtocol.DNS_PLUS_TLS:
                    tls = True
                base += f"\tforward-addr: \"{server.to_unbound_string()}\"\n"
            base += f"\tforward-tls-upstream: {'yes' if tls else 'no'}\n"

        return base

    def configure(self) -> bool:
        """ Configure this instance (Write to unbound config file)

        :return: True on success, otherwise False
        :rtype: bool
        """
        try:
            with open("/run/dnsconfd/unbound.conf", "w",
                      encoding="utf-8") as conf_file:
                conf_file.write(self.get_conf_string())
        except OSError as e:
            self.lgr.critical("Could not write Unbound configuration, %s",
                              e)
            return False

        self.lgr.debug("DNS cache should be listening on %s", self.address)
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
        control_args = ["unbound-control", f"{command}"]
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

    def set_static_options(self,
                           zones_to_servers:
                           dict[str, list[ServerDescription]]) -> bool:
        """ Change static options of manager
        
        :param zones_to_servers: Dictionary mapping zone names to list of
                                 servers
        :return: True if restart is required otherwise False
        """
        for zone, servers in zones_to_servers.items():
            for server in servers:
                if self.current_ca != server.ca:
                    self.current_ca = server.ca
                    return True
        return False

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
        new_zones_to_servers = {}
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
            used_srvs = self._get_used_servers(zones_to_servers[zone])
            add_cmd = self._get_forward_add_command(zone,
                                                    used_srvs)
            if add_cmd is None:
                self.lgr.error("Was not able to construct unbound "
                               "forward_add command for zone %s, it will be "
                               "ignored", zone)
                continue
            if (not self._execute_cmd(add_cmd)
                    or not self._execute_cmd(f"flush_zone {zone}")):
                return False
            new_zones_to_servers[zone] = deepcopy(used_srvs)
        for zone in stable_zones:
            if self.zones_to_servers[zone] == zones_to_servers[zone]:
                self.lgr.debug("Zone %s is the same in old and new "
                               "config thus skipping it", zone)
                new_zones_to_servers[zone] = deepcopy(zones_to_servers[zone])
                continue
            self.lgr.debug("Updating zone %s", zone)
            used_srvs = self._get_used_servers(zones_to_servers[zone])
            add_cmd = self._get_forward_add_command(zone,
                                                    used_srvs)
            # here we do not have to check add_cmd because the zone was
            # already put into unbound, and thus it passed the check
            if (not self._execute_cmd(f"forward_remove +i {zone}")
                    or not self._execute_cmd(add_cmd)
                    or not self._execute_cmd(f"flush_zone {zone}")):
                return False
            new_zones_to_servers[zone] = deepcopy(used_srvs)

        # since we need to break references to ServerDescription objects
        # held before, but keep all the metadata, deepcopy is required
        self.zones_to_servers = new_zones_to_servers
        self.lgr.info("Unbound updated to configuration: %s",
                      self.get_status())
        self._configuration_serial = self._requested_configuration_serial
        return True

    @staticmethod
    def _get_used_servers(servers: list[ServerDescription]):
        max_prio = servers[0].priority
        used_protocol = servers[0].protocol
        # this will remove duplicate servers
        unique_servers = {}
        zone_servers = []

        for srv in servers:
            if srv.protocol == used_protocol and srv.priority == max_prio:
                srv_string = srv.to_unbound_string()
                if srv_string not in unique_servers:
                    unique_servers[srv_string] = True
                    zone_servers.append(srv)
            else:
                break

        return zone_servers

    def _get_forward_add_command(self,
                                 zone: str,
                                 servers: list[ServerDescription]
                                 ) -> Optional[str]:
        used_protocol = servers[0].protocol
        servers_str = []
        # this will remove duplicate servers
        insecure = False
        for srv in servers:
            servers_str.append(srv.to_unbound_string())
            if self.dnssec and not insecure and not srv.dnssec:
                insecure = True
        tls = used_protocol == DnsProtocol.DNS_PLUS_TLS
        flags = None
        if tls or insecure:
            flags = "+"
            for check, flag in [(insecure, "i"), (tls, "t")]:
                if check:
                    flags += flag
            flags += " "
        if zone != "." and HAVE_IDNA:
            encoded_zone = self._idna_encode(zone)
            if encoded_zone is None:
                return None
        else:
            encoded_zone = zone
        return (f"forward_add {flags if flags else ''}"
                f"{encoded_zone} {' '.join(servers_str)}")

    def _idna_encode(self, domain: str) -> Optional[str]:
        try:
            return idna.encode(domain).decode("utf-8")
        except idna.IDNAError as e:
            self.lgr.warning("Zone %s will not be set, because it can "
                             "not be encoded with IDNA: %s", domain, e)
            return None

    def get_status(self) -> dict[str, list[str]]:
        """ Get current forwarders' network_objects that this instance holds

        :return: dictionary mapping zones -> list of servers
        :rtype: dict[str, list[str]]
        """
        status = {}
        for zone, servers in self.zones_to_servers.items():
            status[zone] = [str(srv) for srv in servers]
        return status
