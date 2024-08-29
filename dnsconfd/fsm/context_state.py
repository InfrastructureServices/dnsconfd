from enum import Enum


# states marked with interrupt need to handle INTERFACE_UPDATE,
# FULL_UPDATE and STOP events
class ContextState(Enum):
    """ State the Dnsconfd FSM can be in """
    STARTING = 1  # interrupt
    WAITING_FOR_START_JOB = 2  # interrupt
    POLLING = 3  # interrupt
    RUNNING = 4  # interrupt
    STOPPING = 5
    SETTING_UP_RESOLVCONF = 6
    CONNECTING_DBUS = 7
    SUBMITTING_START_JOB = 8
    UPDATING = 9
    UPDATING_RESOLV_CONF = 10
    UPDATING_DNS_MANAGER = 11
    SUBMITTING_STOP_JOB = 12
    WAITING_STOP_JOB = 13  # interrupt
    REVERTING_RESOLV_CONF = 14
    WAITING_TO_SUBMIT_STOP_JOB = 15  # interrupt
    SUBMITTING_RESTART_JOB = 16
    WAITING_RESTART_JOB = 17  # interrupt
    REVERT_RESOLV_ON_FAILED_RESTART = 18
    CONFIGURING_DNS_MANAGER = 19
    UPDATING_ROUTES = 20
    REMOVING_ROUTES = 21
