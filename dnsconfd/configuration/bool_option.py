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
            self.lgr.error(f"Expected true or false for option {self.name}"
                           f" but {value} was given")
            return False

        return True
