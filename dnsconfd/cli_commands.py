from dnsconfd import NetworkManager
from dnsconfd import SystemManager
import dnsconfd.dbus

from sys import exit
from dbus import DBusException
import dbus
import typing
import json


class CLI_Commands:
    @staticmethod
    def status(dbus_name: str,
               json_format: bool,
               api_choice: str) -> typing.NoReturn:
        """ Call Dnsconfd status method through DBUS and print result

        :param dbus_name: DBUS name Dnsconfd listens on
        :type dbus_name: str
        :param json_format: True if status should be in JSON format
        :type json_format: bool
        :return: No return
        """
        bus = dbus.SystemBus()
        try:
            if api_choice == "resolve1":
                object_path = dnsconfd.dbus.PATH_RESOLVED
                int_name = dnsconfd.dbus.INT_DNSCONFD # "org.freedesktop.resolve1.Dnsconfd"
            else:
                object_path = "/com/redhat/dnsconfd"
                int_name = "com.redhat.dnsconfd.Manager"
            dnsconfd_object = bus.get_object(dbus_name,
                                             object_path)
        except DBusException as e:
            print(f"Dnsconfd is not listening on name {dbus_name}, {e}")
            exit(1)
        try:
            print(dnsconfd_object.Status(json_format,
                                         dbus_interface=int_name))
        except DBusException as e:
            print("Was not able to call Status method, check your DBus policy:"
                  + f"{e}")
            exit(1)
        exit(0)

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
            exit(1)
        print(f"Network Manager will {'use' if enable else 'not use'}"
              + " dnsconfd now")
        exit(0)

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
                object_path = dnsconfd.dbus.PATH_RESOLVED
                int_name = dnsconfd.dbus.INT_DNSCONFD
            else:
                object_path = "/com/redhat/dnsconfd"
                int_name = "com.redhat.dnsconfd.Manager"
            dnsconfd_object = bus.get_object(dbus_name,
                                             object_path)
        except DBusException as e:
            print(f"Dnsconfd is not listening on name {dbus_name}, {e}")
            exit(1)
        try:
            all_ok, msg = dnsconfd_object.Reload(dbus_interface=int_name)
            print(msg)
            exit(0 if all_ok else 1)
        except DBusException as e:
            print("Was not able to call Status method, check your DBus policy:"
                  + f"{e}")
            exit(1)

    @staticmethod
    def chown_resolvconf(config: dict, user: str) -> typing.NoReturn:
        """ Change ownership resolv.conf

        :param config: dictionary containing configuration
        :param user: user that should own resolv.conf
        :return: No return
        """
        if not SystemManager(config).chown_resolvconf(user):
            exit(1)
        exit(0)

    @staticmethod
    def install(config: dict) -> typing.NoReturn:
        """ Perform all required installation steps

        Change NetworkManager configuration and ownership of resolv.conf
        :param config: dictionary containing configuration
        :return: No return
        """
        if (not NetworkManager().enable() or
                not SystemManager(config).chown_resolvconf("dnsconfd")):
            exit(1)
        exit(0)

    @staticmethod
    def uninstall(config: dict) -> typing.NoReturn:
        """ Perform all required uninstallation steps

        Revert NetworkManager configuration and ownership of resolv.conf
        :param config: dictionary containing configuration
        :return: No return
        """
        if (not NetworkManager().disable() or
                not SystemManager(config).chown_resolvconf("root")):
            exit(1)
        exit(0)

    @staticmethod
    def update(dbus_name: str,
               servers: str,
               api_choice: str) -> typing.NoReturn:
        try:
            server_list = json.loads(servers)
        except json.JSONDecodeError as e:
            print("Servers are not valid JSON string")
            exit(1)
        bus = dbus.SystemBus()

        # unfortunately domains have to be converted explicitly,
        # because dbus-python can not guess type of array containing
        # string and boolean
        try:
            for server in server_list:
                if "domains" in server:
                    server["domains"] = [dbus.Struct((dom[0], dom[1]))
                                         for dom in server["domains"]]
        except (IndexError, TypeError) as e:
            print(f"Failed to convert domains, {e}")
            exit(1)

        try:
            if api_choice != "dnsconfd":
                print(f"This command does not support resolve1")
                exit(1)
            dnsconfd_object = bus.get_object(dbus_name,
                                             "/com/redhat/dnsconfd")
            dnsconfd_interface = dbus.Interface(dnsconfd_object,
                                                "com.redhat.dnsconfd.Manager")
        except DBusException as e:
            print(f"Dnsconfd is not listening on name {dbus_name}, {e}")
            exit(1)
        try:
            all_ok, message = dnsconfd_interface.Update(server_list,
                                                        signature="aa{sv}")
            print(f"{message}")
        except DBusException as e:
            print("Was not able to call update method, check your DBus policy:"
                  + f"{e}")
            exit(1)
        exit(0 if all_ok else 1)
