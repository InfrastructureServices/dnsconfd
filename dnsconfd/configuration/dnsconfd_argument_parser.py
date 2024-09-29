import os
import logging
import sys
from argparse import ArgumentParser, BooleanOptionalAction
import yaml
import yaml.scanner

from dnsconfd import CLICommands as Cmds
from dnsconfd.configuration import Option, StaticServersOption, StringOption
from dnsconfd.configuration import IpOption, BoolOption
from dnsconfd.fsm.exit_code import ExitCode


class DnsconfdArgumentParser(ArgumentParser):
    def __init__(self, *args, **kwargs) -> None:
        """ Dnsconfd argument parser

        :param args: arguments for the parent constructor
        :param kwargs: keyword arguments for the parent constructor
        """
        super().__init__(*args, **kwargs)
        self.lgr = logging.getLogger(self.__class__.__name__)
        self._parsed = None
        self._env = os.environ
        dbus_re = r"([A-Za-z_]+[A-Za-z_0-9]*)(.[A-Za-z_]+[A-Za-z_0-9]*)+"
        self._config_values = [
            StringOption("log_level",
                         "Log level of dnsconfd",
                         "INFO",
                         validation=r"DEBUG|INFO|WARNING|ERROR|CRITICAL"),
            StringOption("dbus_name",
                         "DBUS name that dnsconfd should use",
                         "org.freedesktop.resolve1",
                         validation=dbus_re),
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
            StaticServersOption("static_servers",
                                "Map of zones and resolvers that"
                                " should be globally used for them",
                                [],
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
                   in_env=True),
            StringOption("api_choice",
                         "API which should be used",
                         "resolve1",
                         validation=r"resolve1|dnsconfd")
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
                                                     self._parsed.json,
                                                     self._parsed.api_choice))

        reload = subparsers.add_parser("reload",
                                       help="Reload running cache service")
        reload.set_defaults(func=lambda: Cmds.reload(self._parsed.dbus_name,
                                                     self._parsed.api_choice))

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

        reload = subparsers.add_parser("update",
                                       help="update dnsconfd forwarders list")

        reload.add_argument("server_list",
                            default="[]",
                            help="JSON formatted list of servers")
        reload.set_defaults(func=lambda: Cmds.update(self._parsed.dbus_name,
                                                     self._parsed.server_list,
                                                     self._parsed.api_choice))

    @staticmethod
    def _config_log(log_level):
        logging.basicConfig(level=log_level)

    def parse_args(self, *args, **kwargs):
        """ Parse arguments

        :param args: Arguments for the parent parse_args method
        :param kwargs: Keyword arguments for the parent parse_args method
        :return:
        """

        self._parsed = super().parse_args(*args, **kwargs)

        # config will provide defaults
        if self._parsed.config_file is not None:
            config = self._read_config(self._parsed.config_file)
        else:
            config = self._read_config(os.environ.get("CONFIG_FILE",
                                                      "/etc/dnsconfd.conf"))

        log_level = self._get_option_value(config, self._config_values[0])
        self._config_log(log_level)

        for option in self._config_values:
            setattr(self._parsed,
                    option.name,
                    self._get_option_value(config, option))

        return self._parsed

    def _get_option_value(self, config: dict, option: Option):
        final_val = option.default
        if (option.in_file
                and config.get(option.name, None) is not None):
            final_val = config[option.name]
            self.lgr.debug("Applying value %s"
                           " to %s from file", final_val, option.name)
        if (option.in_env
                and self._env.get(option.name.upper(), None) is not None):
            if isinstance(option, BoolOption):
                final_val = self._env[option.name.upper()] in ["yes", "1"]
            else:
                final_val = self._env[option.name.upper()]
            self.lgr.debug("Applying value %s "
                           "to %s from env variable", final_val, option.name)
        if (option.in_args
                and getattr(self._parsed, option.name) is not None):
            final_val = getattr(self._parsed, option.name)
            self.lgr.debug("Applying value %s "
                           "to %s from cmdline", final_val, option.name)
        if not option.validate(final_val):
            raise ValueError

        return final_val

    @staticmethod
    def _open_config_file(path):
        # this method exists mainly for the sake of unit testing
        return open(path, "r", encoding="utf-8")

    def _read_config(self, path: str) -> dict:
        config = {}
        try:
            with self._open_config_file(path) as config_file:
                temp_config = yaml.safe_load(config_file)
            if temp_config is not None:
                config = temp_config
        except OSError as e:
            self.lgr.warning("Could not open configuration file "
                             "at %s, %s", path, e)
            return {}
        except yaml.scanner.ScannerError as e:
            self.lgr.warning("Could not parse configuration file "
                             "at %s, %s", path, e)
            return {}

        if not isinstance(config, dict):
            # yaml library returns string in some cases of invalid input
            self.lgr.warning("Configuration could not be parsed as YAML")
            return {}
        return config
