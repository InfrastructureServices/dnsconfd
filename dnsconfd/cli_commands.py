from dnsconfd.network_manager import NetworkManager

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
        try:
            if enable:
                NetworkManager().enable()
            else:
                NetworkManager().disable()
            print(f"Network Manager will {'use' if enable else 'not use'}"
                  + " dnsconfd now")
            exit(0)
        except Exception as e:
            print("Dnsconfd was unable to configure Network Manager: "
                  + f"{str(e)}")
            exit(1)

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
