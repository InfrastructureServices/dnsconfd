import logging
import json
from typing import Callable

from dnsconfd import SystemManager
from dnsconfd.dns_managers import UnboundManager
from dnsconfd.fsm.exit_code_handler import ExitCodeHandler
from dnsconfd.fsm import ContextEvent, ContextState
from dnsconfd.fsm.transitions import Starting, Running, Stopping
from dnsconfd.routing_manager import RoutingManager
from dnsconfd.server_manager import ServerManager
from dnsconfd.systemd_manager import SystemdManager


class DnsconfdContext:
    def __init__(self,
                 config: dict,
                 main_loop: object):
        """ Class containing implementation of FSM that controls Dnsconfd
        operations

        :param config: dict containing network_objects
        :type config: dict
        :param main_loop: Main loop provided by GLib
        :type main_loop: object
        """
        self.lgr = logging.getLogger(self.__class__.__name__)
        self.dns_mgr = UnboundManager(config)
        self._main_loop = main_loop
        sys_mgr = SystemManager(config)
        self.transitions = {}
        self.state = ContextState.STARTING
        systemd_manager = SystemdManager(self.transition_function)
        self.exit_code_handler = ExitCodeHandler()
        self.server_manager = ServerManager(config)
        self.routing_manager = RoutingManager(self.transition_function)
        self._did_serial_change = False
        self._signal_emitter = None

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
                    self.transition_function,
                    self._signal_serial_change),
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
                       "state: %s, event: %s", self.state, event.name)
        while event is not None:
            if (self.state not in self.transitions
                    or event.name not in self.transitions[self.state]):
                self.lgr.info("Transition not found from %s on %s"
                              ", ignoring", self.state, event.name)
                break

            self.state, callback \
                = self.transitions[self.state][event.name]
            event = callback(event)
            self.lgr.info("New state: %s, new event: %s",
                          self.state,
                          'None' if event is None else event.name)
            if self._signal_emitter is not None and self._did_serial_change:
                self._signal_emitter()
                self._did_serial_change = False
        # a bit of a hack, so loop add functions remove this immediately
        return False

    def get_status(self, json_format: bool) -> str:
        """ Get current status of Dnsconfd

        :param json_format: True if status should be in JSON format
        :return: String with status
        :rtype: str
        """
        self.lgr.debug("Handling request for status")
        servers = [a.to_dict() for a in self.server_manager.get_all_servers()]

        if json_format:
            status = {"service": self.dns_mgr.service_name,
                      "mode": str(self.server_manager.mode),
                      "cache_config": self.dns_mgr.get_status(),
                      "state": self.state.name,
                      "servers": servers}
            return json.dumps(status,
                              ensure_ascii=False).encode("utf-8").decode()

        dumped_resolver_config = json.dumps(self.dns_mgr.get_status(),
                                            indent=4,
                                            ensure_ascii=False)
        dumped_servers = json.dumps(servers,
                                    indent=4,
                                    ensure_ascii=False)

        return (f"Running cache service:\n{self.dns_mgr.service_name}\n"
                f"Resolving mode: {str(self.server_manager.mode)}\n"
                "Config present in service:\n"
                f"{dumped_resolver_config.encode('utf-8').decode()}\n"
                f"State of Dnsconfd:\n{self.state.name}\n"
                "Info about servers: "
                f"{dumped_servers.encode('utf-8').decode()}")

    def get_configuration_serial(self):
        return self.dns_mgr.configuration_serial

    def bump_configuration_serial(self):
        return self.dns_mgr.bump_configuration_serial()

    def reload_service(self) -> tuple[bool, str]:
        """ Perform reload of cache service if possible

        :return: Tuple, True and message on success otherwise False and message
        :rtype: tuple[bool, str]
        """
        if self.state != ContextState.RUNNING:
            return (False, "Reload can not be performed at this time. "
                    + f"Current state: {self.state}")
        self.transition_function(ContextEvent("RELOAD"))
        return True, "Starting reload"

    def get_exit_code(self) -> int:
        """ Get exit code Dnsconfd should stop with

        :return: exit code
        :rtype: int
        """
        return self.exit_code_handler.get_exit_code()

    def _signal_serial_change(self):
        self._did_serial_change = True

    def set_signal_emitter(self, signal_emitter: Callable):
        self._signal_emitter = signal_emitter
