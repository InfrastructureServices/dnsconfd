from dnsconfd.configuration import Option
import ipaddress
import re


class StaticServersOption(Option):
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
        try:
            for zone, addr_list in value.items():
                if not domain_pattern.fullmatch(zone) or len(zone) > 253:
                    self.lgr.error(f"{zone} is not a valid domain")
                    return False
                for resolver in addr_list:
                    resolver: dict
                    if "address" not in resolver.keys():
                        self.lgr.error("missing resolver address "
                                       "specification")
                        return False
                    if "protocol" in resolver.keys():
                        if (resolver["protocol"] != "DoT"
                                and resolver["protocol"] != "plain"):
                            self.lgr.error("protocol contains invalid value")
                            return False
                    if "port" in resolver.keys():
                        if not isinstance(resolver["port"], int):
                            self.lgr.error("port has to be number")
                            return False
                        if resolver["port"] < 1 or resolver["port"] > 65535:
                            self.lgr.error("invalid port number")
                            return False
                    if "sni" in resolver.keys():
                        if not isinstance(resolver["sni"], str):
                            self.lgr.error("invalid sni")
                            return False
                    for key in resolver.keys():
                        if key not in ["address", "protocol", "port", "sni"]:
                            self.lgr.error(f"Invalid property {key}")
                            return False
                    try:
                        ipaddress.ip_address(resolver["address"])
                    except ValueError:
                        self.lgr.error(f"{resolver["address"]} is not"
                                       " valid ip address")
                        return False
            return True
        except AttributeError:
            self.lgr.error(f"Static servers must be map with lists of"
                           f" resolvers, invalid value {value} was given")
            return False
