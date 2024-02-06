import dnsconfd
import dnsconfd.dbus
from dnsconfd.network_manager import NetworkManager

from dbus import DBusException
import dbus
import sys
import enum

class Codes(enum.Enum):
    """Return codes on command line commands."""
    SUCCESS = 0
    ERROR_GENERAL = 1
    ERROR_DBUS_NAME = 2
    ERROR_DBUS_OTHER = 3

class CLI_Commands:
    """Command line small action helpers."""

    @staticmethod
    def _fatal(message, code=Codes.ERROR_GENERAL):
        sys.stderr.write(message+"\n")
        if isinstance(code, Codes):
            code = code.value
        exit(code)

    @staticmethod
    def _get_object(dbus_name=dnsconfd.DEFAULT_DBUS_NAME, path=dnsconfd.dbus.RESOLVED_PATH, bus=dbus.SystemBus()):
        try:
            return bus.get_object(dbus_name, path)
        except DBusException as e:
            CLI_Commands._fatal(f"Dnsconfd is not listening on name {dbus_name}: {e.get_dbus_message()}",
                                Codes.ERROR_DBUS_NAME)

    @staticmethod
    def status(dbus_name=dnsconfd.DEFAULT_DBUS_NAME):
        object = CLI_Commands._get_object(dbus_name)
        try:
            status_str = object.Status(dbus_interface=dnsconfd.dbus.DNSCONFD_IFACE)
            decoder = json.decoder.JSONDecoder()
            status = decoder.decode(status_str)
            print_status(status)
            exit(Codes.SUCCESS.value)
        except json.decoder.JSONDecodeError as e:
            CLI_Commands._fatal(f"Failed to decode JSON: {e}", Codes.ERROR_JSON)
        except DBusException as e:
            CLI_Commands._fatal(f"Error calling Status method: {e}",
                                Codes.ERROR_DBUS_OTHER)

    @staticmethod
    def nm_config(enable: bool):
        try:
            if enable:
                NetworkManager().enable()
                use = 'use'
            else:
                NetworkManager().disable()
                use = 'not use'
            print(f"Network Manager will {use} dnsconfd now")
            exit(Codes.SUCCESS.value)
        except Exception as e:
            CLI_Commands._fatal(f"Dnsconfd was unable to configure Network Manager: {str(e)}",
                                Codes.ERROR_DBUS_OTHER)

    @staticmethod
    def reload(dbus_name=dnsconfd.DEFAULT_DBUS_NAME, plugin=None):
        object = CLI_Commands._get_object(dbus_name)
        try:
            print(object.Reload(plugin, dbus_interface=dnsconfd.dbus.DNSCONFD_IFACE))
            exit(Codes.SUCCESS.value)
        except DBusException as e:
            CLI_Commands._fatal(f"Error calling Reload method: {e}",
                                Codes.ERROR_DBUS_OTHER)
