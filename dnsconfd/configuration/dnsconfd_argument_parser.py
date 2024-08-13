from argparse import ArgumentParser, BooleanOptionalAction
from dnsconfd.cli_commands import CLI_Commands as Cmds
from dnsconfd.configuration import Option, GlobalResolversOption, StringOption
from dnsconfd.configuration import IpOption, BoolOption
from dnsconfd.fsm.exit_code import ExitCode

import os
import yaml
import logging
import sys


class DnsconfdArgumentParser(ArgumentParser):
    def __init__(self, *args, **kwargs) -> None:
        """ Dnsconfd argument parser

        :param args: arguments for the parent constructor
        :param kwargs: keyword arguments for the parent constructor
        """
        super(DnsconfdArgumentParser, self).__init__(*args, **kwargs)
        self.lgr = logging.getLogger(self.__class__.__name__)
        self._parsed = None
        dbus_re = r"([A-Za-z_]+[A-Za-z_0-9]*)(.[A-Za-z_]+[A-Za-z_0-9]*)+"
        self._config_values = [
            StringOption("dbus_name",
                         "DBUS name that dnsconfd should use",
                         "org.freedesktop.resolve1",
                         validation=dbus_re),
            StringOption("log_level",
                         "Log level of dnsconfd",
                         "DEBUG",
                         validation=r"DEBUG|INFO|WARNING|ERROR|CRITICAL"),
            Option("resolv_conf_path",
                   "Path to resolv.conf that the dnsconfd should manage",
                   "/etc/resolv.conf"),
            IpOption("listen_address",
                     "Address on which local resolver listens",
                     "127.0.0.1"),
            BoolOption("prioritize_wire",
                       "If set to yes then wireless interfaces will"
                       " have lower priority",
                       True),
            Option("resolver_options",
                   "Options to be used in resolv.conf"
                   " for alteration of resolver behavior",
                   "edns0 trust-ad"),
            BoolOption("dnssec_enabled",
                       "Enable dnssec record validation",
                       False),
            BoolOption("handle_routing",
                       "Dnsconfd will submit necessary"
                       " routes to routing manager",
                       True),
            GlobalResolversOption("global_resolvers",
                                  "Map of zones and resolvers that"
                                  " should be globally used for ",
                                  {},
                                  in_file=True,
                                  in_args=False,
                                  in_env=False),
            BoolOption("ignore_api",
                       "If enabled, dnsconfd will ignore"
                       " configuration received through API",
                       False,
                       in_file=True,
                       in_args=False,
                       in_env=False),
            Option("config_file",
                   "Path where config file is located",
                   "/etc/dnsconfd.conf",
                   in_file=False,
                   in_args=True,
                   in_env=True)
        ]

    def add_arguments(self):
        """ Set up Dnsconfd arguments """
        for option in self._config_values:
            if not option.in_args:
                continue
            opt_name = f"--{option.name.replace('_', '-')}"
            if isinstance(option, BoolOption):
                self.add_argument(opt_name,
                                  help=option.desc,
                                  default=None,
                                  action=BooleanOptionalAction)
            else:
                self.add_argument(opt_name,
                                  help=option.desc,
                                  default=None)

        self.set_defaults(func=lambda: None)

    def _help_and_exit(self):
        self.print_help()
        sys.exit(ExitCode.BAD_ARGUMENTS.value)

    def add_commands(self):
        """ Set up Dnsconfd commands """
        subparsers = self.add_subparsers(help="Subcommands")

        status = subparsers.add_parser("status",
                                       help="Print status if there is a "
                                            + "running instance")
        status.add_argument("--json",
                            default=False,
                            action="store_true",
                            help="Status should be formatted as JSON string")
        status.set_defaults(func=lambda: Cmds.status(self._parsed.dbus_name,
                                                     self._parsed.json))

        reload = subparsers.add_parser("reload",
                                       help="Reload running cache service")
        reload.set_defaults(func=lambda: Cmds.reload(self._parsed.dbus_name))

        config = subparsers.add_parser("config",
                                       help="Change configuration of "
                                            + "service or host")
        config.set_defaults(func=self._help_and_exit)

        config_subparse = config.add_subparsers(help="Commands changing "
                                                     + "configuration")

        nm_enable = config_subparse.add_parser("nm_enable",
                                               help="Config network manager "
                                                    + "to use dnsconfd")
        nm_enable.set_defaults(func=lambda: Cmds.nm_config(True))

        nm_disable = config_subparse.add_parser("nm_disable",
                                                help="Config network manager "
                                                     + "to not use dnsconfd")
        nm_disable.set_defaults(func=lambda: Cmds.nm_config(False))

        take_resolvconf = (
            config_subparse.add_parser("take_resolvconf",
                                       help="Change ownership of resolv conf, "
                                            "so Dsnconfd does not need root "
                                            "privileges"))
        take_resolvconf.set_defaults(
            func=lambda: Cmds.chown_resolvconf(vars(self._parsed),
                                               "dnsconfd"))

        return_resolvconf = (
            config_subparse.add_parser("return_resolvconf",
                                       help="Return ownership of resolv conf, "
                                            "so root is again the owner"))
        return_resolvconf.set_defaults(
            func=lambda: Cmds.chown_resolvconf(vars(self._parsed),
                                               "root"))

        install = config_subparse.add_parser("install",
                                             help="Perform all installation "
                                                  "steps")
        install.set_defaults(func=lambda: Cmds.install(vars(self._parsed)))
        uninstall = config_subparse.add_parser("uninstall",
                                               help="perform Dnsconfd steps")
        uninstall.set_defaults(func=lambda: Cmds.uninstall(vars(self._parsed)))

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

        for option in self._config_values:
            final_val = option.default
            if (option.in_file
                    and config.get(option.name, None) is not None):
                final_val = config[option.name]
            if (option.in_env
                    and os.environ.get(option.name.upper(), None) is not None):
                if isinstance(option, BoolOption):
                    final_val = os.environ[option.name.upper()] == "yes"
                else:
                    final_val = os.environ[option.name.upper()]
            if (option.in_args
                    and getattr(self._parsed, option.name) is not None):
                final_val = getattr(self._parsed, option.name)
            if not option.validate(final_val):
                raise ValueError

            setattr(self._parsed, option.name, final_val)

        return self._parsed

    def _read_config(self, path: str) -> dict:
        config = {}
        try:
            with open(path, "r") as config_file:
                temp_config = yaml.safe_load(config_file)
            if temp_config is not None:
                config = temp_config
        except OSError as e:
            self.lgr.warning("Could not open configuration file "
                             f"at {path}, {e}")
            return {}

        if not isinstance(config, dict):
            # yaml library returns string in some cases of invalid input
            self.lgr.warning("Configuration could not be parsed as YAML")
            return {}
        return config
