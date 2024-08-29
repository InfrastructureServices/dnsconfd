from typing import Any


class ContextEvent:
    def __init__(self, name: str, data: object = None):
        """ Object representing event meant to be handled by Dnsconfd FSM

        :param name: Name of the event
        :type name: str
        :param data: Data about event, defaults to None
        :type data: object, Optional
        """
        self.name: str = name
        self.data: Any = data
