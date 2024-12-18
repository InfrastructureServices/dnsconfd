import typing
import logging
import dbus.service
from dbus.service import BusName

from dnsconfd.network_objects import ServerDescription, InterfaceConfiguration
from dnsconfd.input_modules import ResolvingMode
from dnsconfd.fsm import DnsconfdContext, ContextEvent


class DnsconfdDbusInterface(dbus.service.Object):
    def __init__(self, runtime_context: DnsconfdContext, config: dict):
        """ Implementation of the Dnsconfd DBUS interface

        :param runtime_context: execution context of Dnsconfd
        :param config: configuration dictionary
        """
        super().__init__(object_path="/com/redhat/dnsconfd",
                         bus_name=BusName(config["dbus_name"],
                                          dbus.SystemBus()))
        self.runtime_context = runtime_context
        self.prio_wire = config["prioritize_wire"]
        self.ignore_api = config["ignore_api"]
        self.dnssec_enabled = config["dnssec_enabled"]
        self.lgr = logging.getLogger(self.__class__.__name__)

    @dbus.service.method(dbus_interface='com.redhat.dnsconfd.Manager',
                         in_signature='aa{sv}u', out_signature='bs')
    def Update(self, servers: list[dict[str, typing.Any]], mode: int) \
            -> tuple[bool, str]:
        """ Update forwarders that should be used

        :param servers: list of dictionaries describing servers.
        Members are described in DBUS API documentation
        :param mode: Resolving mode representing how the servers should be
                     handled
        :return: Tuple with True or False and message with more info
        """
        new_servers = []
        self.lgr.info("Update dbus method called with args: %s", servers)
        if self.ignore_api:
            return True, "Configured to ignore"
        ip_to_interface = {}

        if mode not in [0, 1, 2]:
            msg = f"Mode {mode} not in allowed range 0-2"
            self.lgr.error(msg)
            return False, msg

        for index, server in enumerate(servers):
            self.lgr.debug("processing server: %s", server)

            try:
                serv_desc = ServerDescription.from_dict(server,
                                                        self.dnssec_enabled)
            except ValueError as e:
                msg = f"{index + 1}. Server not valid {e}"
                self.lgr.error(msg)
                return False, msg

            serv_int = serv_desc.interface
            is_wireless = False
            if serv_int:
                if (serv_desc.address in ip_to_interface
                        and ip_to_interface[serv_desc.address] != serv_int):
                    self.lgr.warning("2 servers with the same IP can not "
                                     "be bound to 2 different interfaces, "
                                     "ignoring server with interface %s",
                                     serv_int)
                    continue
                else:
                    ip_to_interface[serv_desc.address] = serv_int
                    is_wireless = (self.prio_wire
                                   and (InterfaceConfiguration.
                                        is_interface_wireless(serv_int)))

            if is_wireless:
                serv_desc.priority = 50

            new_servers.append(serv_desc)
        event = ContextEvent("UPDATE",
                             (new_servers, ResolvingMode(mode)))
        self.runtime_context.transition_function(event)
        return True, "Done"

    @dbus.service.method(dbus_interface='com.redhat.dnsconfd.Manager',
                         in_signature='b', out_signature='s')
    def Status(self, json_format: bool):
        """ Get status of Dnsconfd

        :param json_format: True if output should be JSON
        :return: string with status
        """
        return self.runtime_context.get_status(json_format)

    @dbus.service.method(dbus_interface='com.redhat.dnsconfd.Manager',
                         in_signature='', out_signature='bs')
    def Reload(self) -> tuple[bool, str]:
        """ Reload configuration of underlying cache service

        :return: Tuple with True or False and message with more info
        """
        self.lgr.info("Received request for reload of plugin")
        return self.runtime_context.reload_service()
