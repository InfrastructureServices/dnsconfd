from dnsconfd.configuration import Option


class BoolOption(Option):
    """
    Boolean configuration option
    """

    def validate(self, value) -> bool:
        """ Validate that this value is a boolean

        :param value: given value
        :return: True if value is a boolean otherwise False
        :rtype: bool
        """
        if not isinstance(value, bool):
            self.lgr.error("Expected true or false for option %s"
                           " but %s was given", self.name, value)
            return False

        return True
