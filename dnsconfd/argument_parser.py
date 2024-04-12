from argparse import ArgumentParser
from dnsconfd.cli_commands import CLI_Commands
import os


class DnsconfdArgumentParser(ArgumentParser):
    def __init__(self, *args, **kwargs) -> None:
        """ Dnsconfd argument parser

        :param args: arguments for the parent constructor
        :param kwargs: keyword arguments for the parent constructor
        """
        super(DnsconfdArgumentParser, self).__init__(*args, **kwargs)
        self._parsed = None

    def add_arguments(self):
        """ Set up Dnsconfd arguments """
        self.add_argument("--dbus-name",
                          help="DBUS name that dnsconfd should use",
                          default=None)
        self.add_argument("--log-level",
                          help="Log level of dnsconfd",
                          default=None, choices=["DEBUG", "INFO", "WARN"])
        self.add_argument("--resolv-conf-path",
                          help="Path to resolv.conf that the dnsconfd should "
                               + "manage",
                          default=None)
        self.add_argument("--listen-address",
                          help="Address on which local resolver listens",
                          default="127.0.0.1")
        self.set_defaults(func=lambda: None)

    def add_commands(self):
        """ Set up Dnsconfd commands """
        subparsers = self.add_subparsers(help="Subcommands")

        status = subparsers.add_parser("status",
                                       help="Print status if there is a "
                                            + "running instance")
        status.add_argument("--json",
                            default=False,
                            action="store_true",
                            help="status should be formatted as JSON string")
        status.set_defaults(func=self._print_status)

        reload = subparsers.add_parser("reload",
                                       help="Reload either partially or fully "
                                            + "running instance of dnsconfd")
        reload.set_defaults(func=self._reload)

        config = subparsers.add_parser("config",
                                       help="Change network_objects of "
                                            + "service or host")
        config.set_defaults(func=lambda: self.print_help())

        config_subparse = config.add_subparsers(help="Commands changing "
                                                     + "network_objects")

        nm_enable = config_subparse.add_parser("nm_enable",
                                               help="Config network manager "
                                                    + "to use dnsconfd")
        nm_enable.set_defaults(func=lambda: CLI_Commands.nm_config(True))

        nm_disable = config_subparse.add_parser("nm_disable",
                                                help="Config network manager "
                                                     + "to not use dnsconfd")
        nm_disable.set_defaults(func=lambda: CLI_Commands.nm_config(False))

    def _print_status(self):
        CLI_Commands.status(self._parsed.dbus_name, self._parsed.json)

    def parse_args(self, *args, **kwargs):
        """ Parse arguments

        :param args: Arguments for the parent parse_args method
        :param kwargs: Keyword arguments for the parent parse_args method
        :return:
        """
        self._parsed \
            = super(DnsconfdArgumentParser, self).parse_args(*args, **kwargs)

        if self._parsed.dbus_name is None:
            self._parsed.dbus_name = os.environ.get("DBUS_NAME",
                                                    "com.redhat.dnsconfd")
        if self._parsed.resolv_conf_path is None:
            self._parsed.resolv_conf_path = os.environ.get("RESOLV_CONF_PATH",
                                                           "/etc/resolv.conf")
        if self._parsed.log_level is None:
            self._parsed.log_level = os.environ.get("LOG_LEVEL", "INFO")

        return self._parsed

    def _reload(self):
        CLI_Commands.reload(self._parsed.dbus_name)
