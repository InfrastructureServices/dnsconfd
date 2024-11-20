import logging


class Option:
    def __init__(self,
                 name: str,
                 desc: str,
                 default,
                 in_file: bool = True,
                 in_args: bool = True,
                 in_env: bool = True,
                 validation=None):
        """ Dnsconfd configuration option

        :param name: name of configuration option
        :param desc: description of configuration option
        :param default: default value
        :param in_file: can be entered in configuration file
        :param in_args: can be entered in cmdline arguments
        :param in_env: can be entered through environment variables
        :param validation: data necessary for validation
        """
        self.name = name
        self.desc = f"{desc}, Default is {default}"
        self.default = default
        self.in_file = in_file
        self.in_args = in_args
        self.in_env = in_env
        if not self.in_file and not self.in_env and not self.in_args:
            raise ValueError("Option with no allowed input")
        self.lgr = logging.getLogger(self.__class__.__name__)
        self.validation = validation

    def validate(self, value) -> bool:
        """ Validate that the value is allowed

        :param value: Value that should be validated
        :return: True if value is correct, otherwise False
        :rtype: bool
        """
        return True
