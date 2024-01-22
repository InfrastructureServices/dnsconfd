from dnsconfd.network_manager import NetworkManager

from dbus import DBusException
import dbus


class CLI_Commands:
    @staticmethod
    def status(dbus_name: str):
        bus = dbus.SystemBus()
        try:
            dnsconfd_object = bus.get_object(dbus_name, "/org/freedesktop/resolve1")
        except DBusException as e:
            print(f"Dnsconfd is not listening on name {dbus_name}")
            exit(1)
        try:
            print(dnsconfd_object.Status(dbus_interface='org.freedesktop.resolve1.Dnsconfd'))
        except DBusException as e:
            print("Was not able to call Status method, check your DBus policy")
            exit(1)
        exit(0)

    @staticmethod
    def nm_config(enable: bool):
        try:
            if enable:
                NetworkManager().enable()
            else:
                NetworkManager().disable()
            print(f"Network Manager will {'use' if enable else 'not use'} dnsconfd now")
            exit(0)
        except Exception as e:
            print(f"Dnsconfd was unable to configure Network Manager: {str(e)}")
            exit(1)

    @staticmethod
    def reload(dbus_name, plugin=None):
        bus = dbus.SystemBus()
        try:
            dnsconfd_object = bus.get_object(dbus_name, "/org/freedesktop/resolve1")
        except DBusException as e:
            print(f"Dnsconfd is not listening on name {dbus_name}")
            exit(1)
        try:
            print(dnsconfd_object.Reload(plugin, dbus_interface='org.freedesktop.resolve1.Dnsconfd'))
        except DBusException as e:
            print("Was not able to call Status method, check your DBus policy")
            exit(1)
        exit(0)
