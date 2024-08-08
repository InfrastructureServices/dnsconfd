from argparse import ArgumentParser
from dnsconfd.cli_commands import CLI_Commands as Cmds

import os
import yaml
import logging


class DnsconfdArgumentParser(ArgumentParser):
    def __init__(self, *args, **kwargs) -> None:
        """ Dnsconfd argument parser

        :param args: arguments for the parent constructor
        :param kwargs: keyword arguments for the parent constructor
        """
        super(DnsconfdArgumentParser, self).__init__(*args, **kwargs)
        self.lgr = logging.getLogger(self.__class__.__name__)
        self._parsed = None
        self._config_values = [
            ("dbus_name",
             "DBUS name that dnsconfd should use, default com.redhat.dnsconfd",
             "org.freedesktop.resolve1",
             False),
            ("log_level",
             "Log level of dnsconfd, default DEBUG",
             "DEBUG",
             False),
            ("resolv_conf_path",
             "Path to resolv.conf that the dnsconfd should manage,"
             " default /etc/resolv.conf",
             "/etc/resolv.conf",
             False),
            ("listen_address",
             "Address on which local resolver listens, default 127.0.0.1",
             "127.0.0.1",
             False),
            ("prioritize_wire",
             "If set to yes then wireless interfaces will have lower priority,"
             " default yes",
             True,
             False),
            ("resolver_options",
             "Options to be used in resolv.conf for alteration of resolver "
             "behavior, default 'edns0 trust-ad'",
             "edns0 trust-ad",
             False),
            ("dnssec_enabled",
             "Enable dnssec record validation, default no",
             False,
             False),
            ("handle_routing",
             "Dnsconfd will submit necessary routes to routing manager, "
             "default yes",
             True,
             False),
            ("global_resolvers",
             "Map of zones and resolvers that should be globally used for "
             "them, default {}",
             {},
             True),
            ("ignore_api",
             "If enabled, dnsconfd will ignore configuration received "
             "through API, default no",
             False,
             True)
        ]

    def add_arguments(self):
        """ Set up Dnsconfd arguments """
        for (arg_name, help_str, _, only_file) in self._config_values:
            if only_file:
                continue
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
                            help="Status should be formatted as JSON string")
        status.set_defaults(func=lambda: Cmds.status(self._parsed.dbus_name,
                                                     self._parsed.json))

        reload = subparsers.add_parser("reload",
                                       help="Reload running cache service")
        reload.set_defaults(func=lambda: Cmds.reload(self._parsed.dbus_name))

        config = subparsers.add_parser("config",
                                       help="Change configuration of "
                                            + "service or host")
        config.set_defaults(func=self.print_help)

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

        for (arg_name, help_str, default_val, only_file) in self._config_values:
            if only_file:
                setattr(self._parsed, arg_name, config[arg_name])
            if getattr(self._parsed, arg_name) is None:
                setattr(self._parsed,
                        arg_name,
                        os.environ.get(arg_name.upper(), config[arg_name]))

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
        try:
            for (arg_name, help_str, default_val, _) in self._config_values:
                config.setdefault(arg_name, default_val)
        except AttributeError:
            # this is necessary, because safe_load sometimes returns string
            # when invalid config is provided
            self.lgr.warning("Bad config provided")
            return {arg: val for (arg, _, val, _) in self._config_values}
        for key in config.keys():
            if config[key] == "yes":
                config[key] = True

        return config
