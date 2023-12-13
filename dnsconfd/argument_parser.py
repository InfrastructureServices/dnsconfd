from argparse import ArgumentParser
import os

class DnsconfdArgumentParser(ArgumentParser):
    def __init__(self, *args, **kwargs) -> None:
        super(DnsconfdArgumentParser, self).__init__(*args, **kwargs)
        self.add_argument("-s", "--status",
                          action="store_true",
                          help="Print status of already running instance if any",
                          default=False)
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
        self.add_argument("--enable",
                          help="Activate this service",
                          default=False, const=True, nargs='?')
        self.add_argument("--disable",
                          help="Deactivate this service",
                          default=False, const=True, nargs='?')

    def parse_args(self, *args, **kwargs):
        parsed = super(DnsconfdArgumentParser, self).parse_args(*args, **kwargs)

        if parsed.dbus_name is None:
            parsed.dbus_name = os.environ.get("DBUS_NAME", "com.redhat.dnsconfd")
        if parsed.resolv_conf_path is None:
            parsed.resolv_conf_path = os.environ.get("RESOLV_CONF_PATH",
                                                     "/etc/resolv.conf")
        if parsed.log_level is None:
            parsed.log_level = os.environ.get("LOG_LEVEL", "INFO")

        return parsed
