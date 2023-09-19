from dnsconfd.dns_managers.dns_manager import DnsManager
from dnsconfd.configuration import ServerDescription

import subprocess
import tempfile
import shutil
import logging as lgr


class UnboundManager(DnsManager):
    service_name = "unbound"

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
        lgr.debug(f"Starting unbound process as {' '.join(unbound_args)}")
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
	username: "dnsconfd"
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
        lgr.debug(f"Executing unbound-control as {' '.join(control_args)}")
        proc = subprocess.run(control_args, stdout=subprocess.DEVNULL)
        return proc.returncode

    def update(self, new_zones_to_servers: dict[list[ServerDescription]]):
        lgr.debug("Unbound manager processing update")

        added_zones = [zone for zone in new_zones_to_servers.keys() if zone not in self.zones_to_servers.keys()]
        removed_zones = [zone for zone in self.zones_to_servers.keys() if zone not in new_zones_to_servers.keys()]
        stable_zones = [zone for zone in new_zones_to_servers.keys() if zone in self.zones_to_servers.keys()]

        lgr.debug(f"Update added zones {added_zones}")
        lgr.debug(f"Update removed zones {removed_zones}")
        lgr.debug(f"Zones that were in both configurations {stable_zones}")

        for zone in removed_zones:
            self._execute_cmd(f"forward_remove {zone}")
        for zone in added_zones:
            servers_strings = [srv.to_unbound_string() for srv in new_zones_to_servers[zone]]
            self._execute_cmd(f"forward_add {zone} {' '.join(servers_strings)}")
        for zone in stable_zones:
            if (self.zones_to_servers[zone] == new_zones_to_servers[zone]):
                lgr.debug(f"Zone {zone} is the same in old and new config thus skipping it")
                continue
            lgr.debug(f"Updating zone {zone}")
            self._execute_cmd(f"forward_remove {zone}")
            servers_strings = [srv.to_unbound_string() for srv in new_zones_to_servers[zone]]
            self._execute_cmd(f"forward_add {zone} {' '.join(servers_strings)}")

        self.zones_to_servers = new_zones_to_servers
        lgr.info(f"Unbound updated to configuration: {self.get_status()}")

    def get_status(self):
        status={}
        for zone, servers in self.zones_to_servers.items():
            status[zone] = [str(srv) for srv in servers]
        return status
