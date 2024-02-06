from dnsconfd import NetworkManager
from dnsconfd import SystemManager
import dnsconfd.dbus

from sys import exit
from dbus import DBusException
import dbus
import typing
import sys
import json
import enum
import json.decoder

class Codes(enum.Enum):
    """Return codes on command line commands."""
    SUCCESS = 0
    ERROR_GENERAL = 1
    ERROR_DBUS_NAME = 2
    ERROR_DBUS_OTHER = 3
    ERROR_JSON = 4

def print_status(js):
    print("Service: {service}".format(service=js.get('service')))
    config = js.get('config')
    if config:
        for k in config:
            servers = ' '.join(config[k])
            print("Domain {domain}: {servers}".format(domain=k, servers=servers))

class CLI_Commands:
    """Command line small action helpers."""

    @staticmethod
    def _fatal(message, code=Codes.ERROR_GENERAL):
        sys.stderr.write(message+"\n")
        if isinstance(code, Codes):
            code = code.value
        exit(code)

    @staticmethod
    def _get_object(dbus_name, api_choice):
        if api_choice == "resolve1":
            object_path = dnsconfd.dbus.PATH_RESOLVED
            int_name = dnsconfd.dbus.INT_DNSCONFD
        else:
            object_path = "/com/redhat/dnsconfd"
            int_name = "com.redhat.dnsconfd.Manager"
        bus = dbus.SystemBus()
        dnsconfd_object = bus.get_object(dbus_name,
                                         object_path)
        return (dnsconfd_object, int_name)
        
    @staticmethod
    def print_status(status: object):
        print(status)

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
        try:
            (dnsconfd_object, int_name) = CLI_Commands._get_object(dbus_name, api_choice)
        except DBusException as e:
            CLI_Commands._fatal(f"Dnsconfd is not listening on name {dbus_name}: {e.get_dbus_message()}",
                                Codes.ERROR_DBUS_NAME)

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
    def nm_config(enable: bool) -> typing.NoReturn:
        """ Configure Network Manager whether it should use Dnsconfd

        :param enable: True if Network Manager should use Dnsconfd
        :return: No return
        """
        if enable:
            success = NetworkManager().enable()
            use = 'use'
        else:
            success = NetworkManager().disable()
            use = 'not use'
        if not success:
            CLI_Commands._fatal(f"Dnsconfd was unable to configure Network Manager: {str(e)}",
                                Codes.ERROR_DBUS_OTHER)
        else:
            print(f"Network Manager will {use} dnsconfd now")
            exit(Codes.SUCCESS.value)

    @staticmethod
    def reload(dbus_name=dnsconfd.DEFAULT_DBUS_NAME,
               api_choice: str) -> typing.NoReturn:
        """ Call Dnsconfd reload method through DBUS

        :param api_choice: dnsconfd or resolve1
        :type api_choice: str
        :param dbus_name: DBUS name Dnsconfd listens on
        :type dbus_name: str
        :return: No return
        """
        try:
            (dnsconfd_object, int_name) = CLI_Commands._get_object(dbus_name, api_choice)

            all_ok, msg = dnsconfd_object.Reload(dbus_interface=int_name)
            print(msg)
            exit(not all_ok)
        except DBusException as e:
            CLI_Commands._fatal(f"Error calling Reload method: {e}",
                                Codes.ERROR_DBUS_OTHER)
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
