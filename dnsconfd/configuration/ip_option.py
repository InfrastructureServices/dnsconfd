import ipaddress

from dnsconfd.configuration import Option


class IpOption(Option):
    """
    Ip address configuration option
    """
    def validate(self, value) -> bool:
        """ Validate that the value is an ip address

        :param value: Value that should be validated
        :return: True if value is a string of an ip address, otherwise False
        :rtype: bool
        """
        try:
            ipaddress.ip_address(value)
            return True
        except ValueError:
            self.lgr.error("Value of %s must be an ip address "
                           "%s was given", self.name, value)
            return False
