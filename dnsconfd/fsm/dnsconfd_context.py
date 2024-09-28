from dnsconfd import SystemManager
from dnsconfd.dns_managers import UnboundManager
from dnsconfd.fsm.exit_code_handler import ExitCodeHandler
from dnsconfd.network_objects import InterfaceConfiguration
from dnsconfd.fsm import ContextEvent
from dnsconfd.fsm import ContextState
from dnsconfd.fsm.transitions import Starting, Running, Stopping

import logging
import json

from dnsconfd.routing_manager import RoutingManager
from dnsconfd.server_manager import ServerManager
from dnsconfd.systemd_manager import SystemdManager


class DnsconfdContext:
    def __init__(self, config: dict, main_loop: object):
        """ Class containing implementation of FSM that controls Dnsconfd
        operations

        :param config: dict containing network_objects
        :type config: dict
        :param main_loop: Main loop provided by GLib
        :type main_loop: object
        """
        self.lgr = logging.getLogger(self.__class__.__name__)
        self.dns_mgr = UnboundManager(config["dnssec_enabled"])
        self._main_loop = main_loop
        sys_mgr = SystemManager(config)
        self.transitions = {}
        self.state = ContextState.STARTING
        systemd_manager = SystemdManager(self.transition_function)
        self.exit_code_handler = ExitCodeHandler()
        self.server_manager = ServerManager(config)
        self.routing_manager = RoutingManager(config["prioritize_wire"], self.transition_function)

        transitions_implementations = [
            Starting(config,
                     self.dns_mgr,
                     self.exit_code_handler,
                     self.transition_function,
                     systemd_manager,
                     self.server_manager),
            Running(config,
                    self.dns_mgr,
                    self.exit_code_handler,
                    sys_mgr,
                    systemd_manager,
                    self.server_manager,
                    self.routing_manager,
                    self.transition_function),
            Stopping(config,
                     self.dns_mgr,
                     self.exit_code_handler,
                     sys_mgr,
                     main_loop,
                     systemd_manager,
                     self.routing_manager,
                     self.server_manager)
        ]
        for instance in transitions_implementations:
            for key in instance.transitions:
                if key not in self.transitions:
                    self.transitions[key] = instance.transitions[key]
                else:
                    self.transitions[key].update(instance.transitions[key])

    def transition_function(self, event: ContextEvent) -> bool:
        """ Perform transition based on current state and incoming event

        :param event: Incoming event
        :type event: ContextEvent
        :return: Always false. This allows use in loop callbacks
        """
        self.lgr.debug("FSM transition function called, "
                       f"state: {self.state}, event: {event.name}")
        try:
            while event is not None:
                self.state, callback \
                    = self.transitions[self.state][event.name]
                event = callback(event)
                self.lgr.info(f"New state: {self.state}, new event: "
                              f"{'None' if event is None else event.name}")
        except KeyError:
            self.lgr.error("There is no transition defined from "
                           f"{self.state} on {event.name} event, ignoring")
        # a bit of a hack, so loop add functions remove this immediately
        return False

    def get_status(self, json_format: bool) -> str:
        """ Get current status of Dnsconfd

        :param json_format: True if status should be in JSON format
        :return: String with status
        :rtype: str
        """
        self.lgr.debug("Handling request for status")
        servers = [a.to_dict() for a in self.server_manager.dynamic_servers + self.server_manager.static_servers]
        found_interfaces = {}
        for srv in servers:
            if srv["interface"] is not None:
                found_interfaces[srv["interface"]] = True
        for key in found_interfaces:
            found_interfaces[key] = InterfaceConfiguration.get_if_name(key)
        for srv in servers:
            if srv["interface"] is not None:
                srv["interface"] = found_interfaces[srv["interface"]]

        if json_format:
            status = {"service": self.dns_mgr.service_name,
                      "cache_config": self.dns_mgr.get_status(),
                      "state": self.state.name,
                      "servers": servers}
            return json.dumps(status)
        return (f"Running cache service:\n{self.dns_mgr.service_name}\n"
                "Config present in service:\n"
                f"{json.dumps(self.dns_mgr.get_status(), indent=4)}\n"
                f"State of Dnsconfd:\n{self.state.name}\n"
                "Info about servers: "
                f"{json.dumps(servers, indent=4)}")

    def reload_service(self) -> tuple[bool, str]:
        """ Perform reload of cache service if possible

        :return: Tuple, True and message on success otherwise False and message
        :rtype: tuple[bool, str]
        """
        if self.state != ContextState.RUNNING:
            return (False, "Reload can not be performed at this time. "
                    + f"Current state: {self.state}")
        else:
            self.transition_function(ContextEvent("RELOAD"))
            return True, "Starting reload"

    def get_exit_code(self) -> int:
        """ Get exit code Dnsconfd should stop with

        :return: exit code
        :rtype: int
        """
        return self.exit_code_handler.get_exit_code()
