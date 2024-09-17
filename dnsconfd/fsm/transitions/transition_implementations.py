from dnsconfd.fsm import ContextEvent, SharedContainer, ContextState

from typing import Callable, Type
import logging


class TransitionImplementations:

    def __init__(self,
                 container: SharedContainer,
                 transition_function: Callable):
        self.container = container
        self.lgr = logging.getLogger(self.__class__.__name__)
        self.transitions: dict[
            ContextState,
            dict[str,
                 tuple[ContextState,
                       Callable[[Type["TransitionImplementations"],
                                 ContextEvent],
                                ContextEvent]]]] = {}
        self.transition_function = transition_function
