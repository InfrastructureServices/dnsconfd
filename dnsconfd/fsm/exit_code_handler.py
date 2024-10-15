from dnsconfd import ExitCode


class ExitCodeHandler:
    def __init__(self):
        """ Object responsible for handling of dnsconfd exit code """
        self.exit_code = 0

    def set_exit_code(self, code: ExitCode):
        """ Set exit code

        :param code: code that should be set if possible, if a code
        was already set then calling this has no effect
        """
        if self.exit_code == 0:
            self.exit_code = code.value

    def get_exit_code(self):
        """ Get contained exit code

        :return: Contained exit code
        """
        return self.exit_code
