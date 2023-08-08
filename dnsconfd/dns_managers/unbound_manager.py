from dnsconfd.dns_managers.dns_manager import DnsManager
from dnsconfd.configuration import InterfaceConfiguration
from dnsconfd.configuration import ServerDescription

import subprocess
import tempfile
import shutil
import logging as lgr


class UnboundManager(DnsManager):
    def __init__(self):
        self.temp_dir_path = None
        self.process = None
        self.zones_to_servers = {}

    def configure(self):
        if self.temp_dir_path is None:
            self.temp_dir_path = tempfile.mkdtemp()
        lgr.debug(f"Constructing Unbound configuration into {self.temp_dir_path}/unbound.conf")
        with open(f"{self.temp_dir_path}/unbound.conf", "w") as conf_file:
            conf_file.write(self._constructConfigurationFile())

    def start(self):
        unbound_args = ["/usr/sbin/unbound", "-d", "-p", "-c", f"{self.temp_dir_path}/unbound.conf"]
        lgr.info(f"Starting unbound process as {' '.join(unbound_args)}")
        self.process = subprocess.Popen(args=unbound_args)

    def _constructConfigurationFile(self) -> str:
        # TODO adapt this setting to number of working cpus
        # TODO configuration of validator and debug messages
        # about the upstream server not supporting DNSSEC
        conf = f"""
server:
	verbosity: 1
	statistics-interval: 0
	statistics-cumulative: no
	extended-statistics: yes
	num-threads: 4
	interface-automatic: no
    interface: 127.0.0.53
	outgoing-port-permit: 32768-60999
	outgoing-port-avoid: 0-32767
	outgoing-port-avoid: 61000-65535
	so-reuseport: yes
	ip-transparent: yes
	max-udp-size: 3072
	edns-tcp-keepalive: yes
	chroot: ""
	username: "unbound"
	directory: "{self.temp_dir_path}"
	log-time-ascii: yes
    use-syslog: no
    logfile: "/var/log/dnsconfd/unbound.log"
	harden-glue: yes
	harden-dnssec-stripped: yes
	harden-below-nxdomain: yes
	harden-referral-path: yes
	qname-minimisation: yes
	aggressive-nsec: yes
	unwanted-reply-threshold: 10000000
	prefetch: yes
	prefetch-key: yes
	deny-any: yes
	rrset-roundrobin: yes
	minimal-responses: yes
	module-config: "ipsecmod iterator"
	trust-anchor-signaling: yes
	root-key-sentinel: yes
	trusted-keys-file: /etc/unbound/keys.d/*.key
	auto-trust-anchor-file: "/var/lib/unbound/root.key"
	val-clean-additional: yes
	val-permissive-mode: no
	serve-expired: yes
	serve-expired-ttl: 14400
	val-log-level: 1
	tls-ciphers: "PROFILE=SYSTEM"
	ede: yes
	ede-serve-expired: yes
	ipsecmod-enabled: no
	ipsecmod-hook:/usr/libexec/ipsec/_unbound-hook
remote-control:
	control-enable: yes
	control-use-cert: "no"
        """
        return conf

    def stop(self):
        if self.process is None:
            return
        lgr.info("Stoping Unbound")
        self.process.kill()
        self.process = None

    def clean(self):
        lgr.debug("Performing cleanup after unbound")
        shutil.rmtree(self.temp_dir_path)
        self.temp_dir_path = None

    def _execute_cmd(self, command: str):
        control_args = ["unbound-control", "-c", f"{self.temp_dir_path}/unbound.conf", f'{command}']
        lgr.info(f"Executing unbound-control as {' '.join(control_args)}")
        proc = subprocess.run(control_args)
        return proc.returncode

    def update_interface(self, old_interface_config: InterfaceConfiguration,
                         new_interface_config: InterfaceConfiguration):
        lgr.debug(f"Unbound updating interface {old_interface_config} "
                  + f"with {new_interface_config}")
        if old_interface_config is None:
            # this update only interests unbound only if the interface is supposed to handle
            # some domains or it is considered default
            zones = []
            if new_interface_config.is_default:
                lgr.debug("New interface configuration is default and thus adding . to its domains")
                zones.append(".")
            zones.extend(new_interface_config.domains)
            self._add_servers_to_zones(zones, new_interface_config.servers)
        else:
            # now find out if there is a difference between domains of old config and new config
            added_domains = list(filter(lambda x: x not in old_interface_config.domains,
                                   new_interface_config.domains))
            removed_domains = list(filter(lambda x: x not in new_interface_config.domains,
                                     old_interface_config.domains))
            stable_domains = [a for a in new_interface_config.domains if a in old_interface_config.domains]
            added_servers = list(filter(lambda x: x not in old_interface_config.servers,
                                   new_interface_config.servers))
            removed_servers = list(filter(lambda x: x not in new_interface_config.servers,
                                     old_interface_config.servers))

            if old_interface_config.is_default:
                # this interface servers have to be removed from root forward zone
                if new_interface_config.is_default:
                    stable_domains.append(".")
                else:
                    removed_domains.append(".")
            elif new_interface_config.is_default:
                added_domains.append(".")

            self._remove_servers_from_zones(removed_domains, old_interface_config.servers)
            self._add_servers_to_zones(added_domains, new_interface_config.servers)
            self._remove_servers_from_zones(stable_domains, removed_servers)
            self._add_servers_to_zones(stable_domains, added_servers)

    def _remove_servers_from_zones(self, zones: list[str], servers: list[ServerDescription]):
        if len(servers) == 0:
            return
        for zone in zones:
            lgr.debug(f"Removing servers {servers} from zone {zone}")
            for server in servers:
                self.zones_to_servers: dict[list[ServerDescription]]
                self.zones_to_servers[zone].remove(server)
            self._execute_cmd(f"forward_remove {zone}")
            if len(self.zones_to_servers[zone]) != 0:
                srvs = " ".join([a.to_unbound_string() for a in self.zones_to_servers[zone]])
                self._execute_cmd(f"forward_add {zone} {srvs}")
            else:
                self.zones_to_servers.pop(zone)
    
    def _add_servers_to_zones(self, zones: list[str], servers: list[ServerDescription]):
        if len(servers) == 0:
            return
        for zone in zones:
            lgr.debug(f"Adding servers {servers} to zone {zone}")
            self.zones_to_servers[zone] = self.zones_to_servers.get(zone, [])
            for server in servers:
                self.zones_to_servers: dict[list[ServerDescription]]
                self.zones_to_servers[zone].append(server)
            self._execute_cmd(f"forward_remove {zone}")
            srvs = " ".join([a.to_unbound_string() for a in self.zones_to_servers[zone]])
            self._execute_cmd(f"forward_add {zone} {srvs}")
