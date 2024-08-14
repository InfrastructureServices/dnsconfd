from enum import Enum


class ExitCode(Enum):
    """ Exit codes used by Dnsconfd """
    GRACEFUL_STOP = 0
    SERVICE_FAILURE = 8
    DBUS_FAILURE = 9
    RESOLV_CONF_FAILURE = 10
    CONFIG_FAILURE = 11
    ROUTE_FAILURE = 12
    BAD_ARGUMENTS = 13
