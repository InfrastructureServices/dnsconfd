import logging

from dnsconfd.configuration import Option
import ipaddress
import re


class GlobalResolversOption(Option):
    """ Global resolvers option

    Since it is quite unique, it is worth it to have its own class
    """
    def validate(self, value) -> bool:
        """ Validate that the value is indeed mapping zones to list of servers

        :param value: given value
        :return: True if the map is correct, otherwise False
        :rtype: bool
        """
        domain_re = r"((?!-)([A-Za-z0-9-]){1,63}(?<!-)\.?)+|\."
        domain_pattern = re.compile(domain_re)
        addr_pattern = re.compile(r"([0-9.:a-fA-F]+)(@[0-9]{1,5})?(#.+)?")
        try:
            for zone, addr_list in value.items():
                if not domain_pattern.fullmatch(zone) or len(zone) > 253:
                    self.lgr.error(f"{zone} is not a valid domain")
                    return False
                for addr in addr_list:
                    is_addr = addr_pattern.fullmatch(addr)
                    if is_addr is None:
                        self.lgr.error(f"{addr} is not in allowed format")
                    try:
                        ipaddress.ip_address(is_addr.group(1))
                    except ValueError:
                        self.lgr.error(f"{addr} is not valid ip address")
            return True
        except AttributeError:
            logging.error(f"Global resolvers must be map with lists of ip"
                          f" addresses, invalid value {value} was given")
            return False
