from dnsconfd.configuration import Option
import ipaddress


class IpOption(Option):
    """
    Ip address configuration option
    """
    def validate(self, value) -> bool:
        """ Validate that the value is an ip address

        :param value:
        :return: True if value is a string of an ip address, otherwise False
        :rtype: bool
        """
        try:
            ipaddress.ip_address(value)
            return True
        except ValueError:
            self.lgr.error(f"Value of {self.name} must be an ip address"
                           f" {value} was given")
            return False
