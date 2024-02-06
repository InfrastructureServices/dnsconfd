import dnsconfd
import dnsconfd.dbus
from dnsconfd.network_manager import NetworkManager

from dbus import DBusException
import dbus
import sys


class CLI_Commands:
    """Command line small action helpers."""

    @staticmethod
    def _fatal(message):
        sys.stderr.write(message+"\n")
        exit(1)
            
    @staticmethod
    def _get_object(dbus_name=dnsconfd.DEFAULT_DBUS_NAME, path=dnsconfd.dbus.RESOLVED_PATH, bus=dbus.SystemBus()):
        try:
            return bus.get_object(dbus_name, path)
        except DBusException as e:
            CLI_Commands._fatal(f"Dnsconfd is not listening on name {dbus_name}: {e.get_dbus_message()}")
    
    @staticmethod
    def status(dbus_name=dnsconfd.DEFAULT_DBUS_NAME):
        object = CLI_Commands._get_object(dbus_name)
        try:
            status = object.Status(dbus_interface=dnsconfd.dbus.DNSCONFD_IFACE)
            print(status)
        except DBusException as e:
            CLI_Commands._fatal(f"Error calling Status method: {e}")
        exit(0)

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
            exit(0)
        except Exception as e:
            CLI_Commands._fatal(f"Dnsconfd was unable to configure Network Manager: {str(e)}")

    @staticmethod
    def reload(dbus_name=dnsconfd.DEFAULT_DBUS_NAME, plugin=None):
        object = CLI_Commands._get_object(dbus_name) 
        try:
            print(object.Reload(plugin, dbus_interface=dnsconfd.dbus.DNSCONFD_IFACE))
        except DBusException as e:
            CLI_Commands._fatal(f"Error calling Reload method: {e}")
        exit(0)
