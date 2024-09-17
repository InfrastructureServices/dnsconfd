from dnsconfd.fsm import ContextEvent
from dnsconfd.fsm.transitions import TransitionImplementations


class WithExit(TransitionImplementations):

    def _exit_transition(self, event: ContextEvent):
        """ Transition to STOPPING

        Save exit code and stop main loop

        :param event: Event holding exit code in data
        :type event: ContextEvent
        :return: None
        :rtype: ContextEvent | None
        """
        self.lgr.info("Stopping event loop and FSM")
        self.container.main_loop.quit()
        return None
