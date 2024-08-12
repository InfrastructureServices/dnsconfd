from dnsconfd.configuration import Option
import re


class StringOption(Option):
    """ String configuration option """

    def validate(self, value) -> bool:
        """ Validate that the value conforms to validation regular expression

        :param value: value given
        :return: True if the value conforms to validation regular expression,
        otherwise False
        :rtype: bool
        """
        pattern = re.compile(self.validation)

        if pattern.fullmatch(value) is None:
            self.lgr.error(f"Value of {self.name} must conform to regular"
                           f" expression {pattern.pattern},"
                           f" {value} was given")
            return False
        return True
