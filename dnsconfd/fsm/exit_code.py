from enum import Enum


class ExitCode(Enum):
    """ Exit codes used by Dnsconfd """
    GRACEFUL_STOP = 0
    SERVICE_FAILURE = 1
    DBUS_FAILURE = 2
    RESOLV_CONF_FAILURE = 3
