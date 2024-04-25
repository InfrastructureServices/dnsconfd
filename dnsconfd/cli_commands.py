from dnsconfd import NetworkManager
from dnsconfd import SystemManager

from dbus import DBusException
import dbus


class CLI_Commands:
    @staticmethod
    def status(dbus_name: str, json_format: bool):
        """ Call Dnsconfd status method through DBUS and print result

        :param dbus_name: DBUS name Dnsconfd listens on
        :type dbus_name: str
        :param json_format: True if status should be in JSON format
        :type json_format: bool
        """
        bus = dbus.SystemBus()
        try:
            dnsconfd_object = bus.get_object(dbus_name,
                                             "/org/freedesktop/resolve1")
        except DBusException as e:
            print(f"Dnsconfd is not listening on name {dbus_name}, {e}")
            exit(1)
        try:
            int_name = "org.freedesktop.resolve1.Dnsconfd"
            print(dnsconfd_object.Status(json_format,
                                         dbus_interface=int_name))
        except DBusException as e:
            print("Was not able to call Status method, check your DBus policy:"
                  + f"{e}")
            exit(1)
        exit(0)

    @staticmethod
    def nm_config(enable: bool):
        """ Configure Network Manager whether it should use Dnsconfd

        :param enable: True if Network Manager should use Dnsconfd
        """
        if enable:
            success = NetworkManager().enable()
        else:
            success = NetworkManager().disable()
        if not success:
            print("Dnsconfd was unable to configure Network Manager")
            exit(1)
        print(f"Network Manager will {'use' if enable else 'not use'}"
              + " dnsconfd now")
        exit(0)

    @staticmethod
    def reload(dbus_name: str):
        """ Call Dnsconfd reload method through DBUS

        :param dbus_name: DBUS name Dnsconfd listens on
        :type dbus_name: str
        """
        bus = dbus.SystemBus()
        try:
            dnsconfd_object = bus.get_object(dbus_name,
                                             "/org/freedesktop/resolve1")
        except DBusException as e:
            print(f"Dnsconfd is not listening on name {dbus_name}, {e}")
            exit(1)
        try:
            int_name = "org.freedesktop.resolve1.Dnsconfd"
            print(dnsconfd_object.Reload(dbus_interface=int_name))
        except DBusException as e:
            print("Was not able to call Status method, check your DBus policy:"
                  + f"{e}")
            exit(1)
        exit(0)

    @staticmethod
    def chown_resolvconf(config: dict, user: str):
        if not SystemManager(config).chown_resolvconf(user):
            exit(1)
        exit(0)

    @staticmethod
    def install(config: dict):
        if (not NetworkManager().enable() or
                not SystemManager(config).chown_resolvconf("dnsconfd")):
            exit(1)
        exit(0)

    @staticmethod
    def uninstall(config: dict):
        if (not NetworkManager().disable() or
                not SystemManager(config).chown_resolvconf("root")):
            exit(1)
        exit(0)
