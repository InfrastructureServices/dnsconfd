from dnsconfd.fsm import ContextEvent
from dnsconfd.fsm.transitions import TransitionImplementations


class WithDeferredUpdate(TransitionImplementations):

    def _update_transition(self, event: ContextEvent):
        """ Transition to the same state

        Save received network_objects and stay in the current state

        :param event: event with interface config in data
        :type event: ContextEvent
        :return: None
        :rtype: ContextEvent | None
        """
        if event.data is None:
            return None
        self.container.servers = event.data
        return None
