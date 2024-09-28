from dnsconfd.dns_managers import UnboundManager
from dnsconfd.fsm import ContextEvent, ContextState

from typing import Callable, Type
import logging

from dnsconfd.fsm.exit_code_handler import ExitCodeHandler


class TransitionImplementations:

    def __init__(self,
                 config: dict,
                 dns_mgr: UnboundManager,
                 exit_code_handler: ExitCodeHandler):
        self.lgr = logging.getLogger(self.__class__.__name__)
        self.config = config
        self.dns_mgr = dns_mgr
        self.exit_code_handler = exit_code_handler
        self.transitions: dict[
            ContextState,
            dict[str,
                 tuple[ContextState,
                       Callable[[Type["TransitionImplementations"],
                                 ContextEvent],
                                ContextEvent]]]] = {}
