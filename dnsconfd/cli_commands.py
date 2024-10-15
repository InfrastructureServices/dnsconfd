import sys
import typing
import json
from dbus import DBusException
import dbus

from dnsconfd import NetworkManager, SystemManager


class CLICommands:
    @staticmethod
    def status(dbus_name: str,
               json_format: bool,
               api_choice: str) -> typing.NoReturn:
        """ Call Dnsconfd status method through DBUS and print result

        :param api_choice: choice of which api should be used dnsconfd or
        resolve1
        :param dbus_name: DBUS name Dnsconfd listens on
        :type dbus_name: str
        :param json_format: True if status should be in JSON format
        :type json_format: bool
        :return: No return
        """
        bus = dbus.SystemBus()
        try:
            if api_choice == "resolve1":
                object_path = "/org/freedesktop/resolve1"
                int_name = "org.freedesktop.resolve1.Dnsconfd"
            else:
                object_path = "/com/redhat/dnsconfd"
                int_name = "com.redhat.dnsconfd.Manager"
            dnsconfd_object = bus.get_object(dbus_name,
                                             object_path)
        except DBusException as e:
            print(f"Dnsconfd is not listening on name {dbus_name}, {e}")
            sys.exit(1)
        try:
            print(dnsconfd_object.Status(json_format,
                                         dbus_interface=int_name))
        except DBusException as e:
            print("Was not able to call Status method, check your DBus policy:"
                  + f"{e}")
            sys.exit(1)
        sys.exit(0)

    @staticmethod
    def nm_config(enable: bool) -> typing.NoReturn:
        """ Configure Network Manager whether it should use Dnsconfd

        :param enable: True if Network Manager should use Dnsconfd
        :return: No return
        """
        if enable:
            success = NetworkManager().enable()
        else:
            success = NetworkManager().disable()
        if not success:
            print("Dnsconfd was unable to configure Network Manager")
            sys.exit(1)
        print(f"Network Manager will {'use' if enable else 'not use'}"
              + " dnsconfd now")
        sys.exit(0)

    @staticmethod
    def reload(dbus_name: str,
               api_choice: str) -> typing.NoReturn:
        """ Call Dnsconfd reload method through DBUS

        :param api_choice: dnsconfd or resolve1
        :type api_choice: str
        :param dbus_name: DBUS name Dnsconfd listens on
        :type dbus_name: str
        :return: No return
        """
        bus = dbus.SystemBus()
        try:
            if api_choice == "resolve1":
                object_path = "/org/freedesktop/resolve1"
                int_name = "org.freedesktop.resolve1.Dnsconfd"
            else:
                object_path = "/com/redhat/dnsconfd"
                int_name = "com.redhat.dnsconfd.Manager"
            dnsconfd_object = bus.get_object(dbus_name,
                                             object_path)
        except DBusException as e:
            print(f"Dnsconfd is not listening on name {dbus_name}, {e}")
            sys.exit(1)
        try:
            all_ok, msg = dnsconfd_object.Reload(dbus_interface=int_name)
            print(msg)
            sys.exit(0 if all_ok else 1)
        except DBusException as e:
            print("Was not able to call Status method, check your DBus policy:"
                  + f"{e}")
            sys.exit(1)

    @staticmethod
    def chown_resolvconf(config: dict, user: str) -> typing.NoReturn:
        """ Change ownership resolv.conf

        :param config: dictionary containing configuration
        :param user: user that should own resolv.conf
        :return: No return
        """
        if not SystemManager(config).chown_resolvconf(user):
            sys.exit(1)
        sys.exit(0)

    @staticmethod
    def install(config: dict) -> typing.NoReturn:
        """ Perform all required installation steps

        Change NetworkManager configuration and ownership of resolv.conf
        :param config: dictionary containing configuration
        :return: No return
        """
        if (not NetworkManager().enable() or
                not SystemManager(config).chown_resolvconf("dnsconfd")):
            sys.exit(1)
        sys.exit(0)

    @staticmethod
    def uninstall(config: dict) -> typing.NoReturn:
        """ Perform all required uninstallation steps

        Revert NetworkManager configuration and ownership of resolv.conf
        :param config: dictionary containing configuration
        :return: No return
        """
        if (not NetworkManager().disable() or
                not SystemManager(config).chown_resolvconf("root")):
            sys.exit(1)
        sys.exit(0)

    @staticmethod
    def update(dbus_name: str,
               servers: str,
               mode: int,
               api_choice: str) -> typing.NoReturn:
        """ Call Update DBUS method of Dnsconfd

        :param dbus_name: DBUS name Dnsconfd listens on
        :param servers: JSON string with servers that should be set in place
        :param mode: Resolving mode that should be set
        :param api_choice: dnsconfd or resolve1
        """
        try:
            server_list = json.loads(servers)
        except json.JSONDecodeError as e:
            print(f"Servers are not valid JSON string: {e}")
            sys.exit(1)
        bus = dbus.SystemBus()

        try:
            if api_choice != "dnsconfd":
                print("This command does not support resolve1")
                sys.exit(1)
            dnsconfd_object = bus.get_object(dbus_name,
                                             "/com/redhat/dnsconfd")
            dnsconfd_interface = dbus.Interface(dnsconfd_object,
                                                "com.redhat.dnsconfd.Manager")
        except DBusException as e:
            print(f"Dnsconfd is not listening on name {dbus_name}, {e}")
            sys.exit(1)
        try:
            all_ok, message = dnsconfd_interface.Update(server_list,
                                                        mode,
                                                        signature="aa{sv}u")
            print(f"{message}")
        except DBusException as e:
            print("Was not able to call update method, check your DBus policy:"
                  + f"{e}")
            sys.exit(1)
        sys.exit(0 if all_ok else 1)
