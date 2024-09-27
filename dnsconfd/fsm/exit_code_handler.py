from dnsconfd.fsm import ExitCode


class ExitCodeHandler:
    def __init__(self):
        self.exit_code = 0

    def set_exit_code(self, code: ExitCode):
        if self.exit_code == 0:
            self.exit_code = code.value

    def get_exit_code(self):
        return self.exit_code
