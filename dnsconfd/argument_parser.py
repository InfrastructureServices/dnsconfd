from argparse import ArgumentParser
from dnsconfd.cli_commands import CLI_Commands

import os
import yaml
import logging as lgr


class DnsconfdArgumentParser(ArgumentParser):
    def __init__(self, *args, **kwargs) -> None:
        """ Dnsconfd argument parser

        :param args: arguments for the parent constructor
        :param kwargs: keyword arguments for the parent constructor
        """
        super(DnsconfdArgumentParser, self).__init__(*args, **kwargs)
        self._parsed = None
        self._config_values = [
            ("dbus_name",
             "DBUS name that dnsconfd should use, default com.redhat.dnsconfd",
             "com.redhat.dnsconfd"),
            ("log_level",
             "Log level of dnsconfd, default INFO",
             "INFO"),
            ("resolv_conf_path",
             "Path to resolv.conf that the dnsconfd should manage,"
             " default /etc/resolv.conf",
             "/etc/resolv.conf"),
            ("listen_address",
             "Address on which local resolver listens, default 127.0.0.1",
             "127.0.0.1"),
            ("prioritize_wire",
             "If set to yes then wireless interfaces will have lower priority,"
             " default yes",
             True)
        ]

    def add_arguments(self):
        """ Set up Dnsconfd arguments """
        for (arg_name, help_str, _) in self._config_values:
            self.add_argument(f"--{arg_name.replace('_', '-')}",
                              help=help_str,
                              default=None)
        self.add_argument("--config-file",
                          help="Path where config file is located,"
                               " default /etc/dnsconfd.conf",
                          default=None)
        # TODO also check env vars

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

        self._parsed = (super(DnsconfdArgumentParser, self)
                        .parse_args(*args, **kwargs))

        # config will provide defaults
        if self._parsed.config_file is not None:
            config = self._read_config(self._parsed.config_file)
        else:
            config = self._read_config(os.environ.get("CONFIG_FILE",
                                                      "/etc/dnsconfd.conf"))

        for (arg_name, help_str, default_val) in self._config_values:
            if getattr(self._parsed, arg_name) is None:
                setattr(self._parsed,
                        arg_name,
                        os.environ.get(arg_name.upper(), config[arg_name]))

        return self._parsed

    def _read_config(self, path: str) -> dict:
        try:
            with open(path, "r") as config_file:
                config = yaml.safe_load(config_file)
        except OSError as e:
            lgr.warning(f"Could not open configuration file at {path}, {e}")
        finally:
            for (arg_name, help_str, default_val) in self._config_values:
                config.setdefault(arg_name, default_val)

        return config

    def _reload(self):
        CLI_Commands.reload(self._parsed.dbus_name)
