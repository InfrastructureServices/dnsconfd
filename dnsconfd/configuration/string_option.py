import re

from dnsconfd.configuration import Option


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
            self.lgr.error("Value of %s must conform to regular expression "
                           " %s, but %s was given",
                           self.name, pattern.pattern, value)
            return False
        return True
