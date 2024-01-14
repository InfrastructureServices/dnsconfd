from argparse import ArgumentParser
from dnsconfd.cli_commands import CLI_Commands
import os


class DnsconfdArgumentParser(ArgumentParser):
    def __init__(self, *args, **kwargs) -> None:
        super(DnsconfdArgumentParser, self).__init__(*args, **kwargs)
        self._parsed = None

        self.add_argument("--dbus-name",
                          help="DBUS name that dnsconfd should use",
                          default=None)
        self.add_argument("--log-level",
                          help="Log level of dnsconfd",
                          default=None, choices=["DEBUG", "INFO", "WARN"])
        self.add_argument("--resolv-conf-path",
                          help="Path to resolv.conf that the dnsconfd should manage",
                          default=None)
        self.add_argument("--listen-address",
                          help="Address on which local resolver listens",
                          default="127.0.0.1")
        self.set_defaults(func=lambda: None)

        subparsers = self.add_subparsers(help="Subcommands")
        
        status_parser = subparsers.add_parser("status",
                                              help="Print status if there is a running instance")
        status_parser.set_defaults(func=lambda: CLI_Commands.status(self._parsed.dbus_name))

        config_parser = subparsers.add_parser("config",
                                              help="Change configuration of service or host")
        config_parser.set_defaults(func=lambda: self.print_help())

        config_subparsers = config_parser.add_subparsers(help="Commands changing configuration")

        nm_enable_parser = config_subparsers.add_parser("nm_enable",
                                                        help="Config network manager to use dnsconfd")
        nm_enable_parser.set_defaults(func=lambda: CLI_Commands.nmConfig(True))
        
        nm_disable_parser = config_subparsers.add_parser("nm_disable",
                                                         help="Config network manager to not use dnsconfd")
        nm_disable_parser.set_defaults(func=lambda: CLI_Commands.nmConfig(False))

    def parse_args(self, *args, **kwargs):
        self._parsed = super(DnsconfdArgumentParser, self).parse_args(*args, **kwargs)

        if self._parsed.dbus_name is None:
            self._parsed.dbus_name = os.environ.get("DBUS_NAME", "com.redhat.dnsconfd")
        if self._parsed.resolv_conf_path is None:
            self._parsed.resolv_conf_path = os.environ.get("RESOLV_CONF_PATH",
                                                     "/etc/resolv.conf")
        if self._parsed.log_level is None:
            self._parsed.log_level = os.environ.get("LOG_LEVEL", "INFO")

        return self._parsed
