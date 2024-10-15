import ipaddress
import re

from dnsconfd.configuration import Option


class StaticServersOption(Option):
    """ Global resolvers option

    Since it is quite unique, it is worth it to have its own class
    """

    def validate(self, value) -> bool:
        """ Validate that the value is indeed list of servers

        :param value: given value
        :return: True if the list is correct, otherwise False
        :rtype: bool
        """
        domain_re = r"((?!-)([A-Za-z0-9-]){1,63}(?<!-)\.?)+|\."
        search_re = r"((?!-)([A-Za-z0-9-]){1,63}(?<!-)\.?)+"
        domain_pattern = re.compile(domain_re)
        search_pattern = re.compile(search_re)
        try:
            if not isinstance(value, list):
                self.lgr.error("static_servers is not a list")
                return False
            for resolver in value:
                resolver: dict
                if "address" not in resolver:
                    self.lgr.error("missing resolver address "
                                   "specification")
                    return False
                if "protocol" in resolver:
                    if (resolver["protocol"] != "DoT"
                            and resolver["protocol"] != "plain"):
                        self.lgr.error("protocol contains invalid value")
                        return False
                if "port" in resolver:
                    if not isinstance(resolver["port"], int):
                        self.lgr.error("port has to be number")
                        return False
                    if resolver["port"] < 1 or resolver["port"] > 65535:
                        self.lgr.error("invalid port number")
                        return False
                if "name" in resolver:
                    if not isinstance(resolver["name"], str):
                        self.lgr.error("invalid name")
                        return False
                if "routing_domains" in resolver:
                    if not isinstance(resolver["routing_domains"], list):
                        self.lgr.error("routing_domains must be a list")
                        return False
                    for domain in resolver["routing_domains"]:
                        if not isinstance(domain, str):
                            self.lgr.error("Each routing domain must be a"
                                           " string")
                            return False
                        if not domain_pattern.fullmatch(domain):
                            self.lgr.error("invalid routing domain %s",
                                           domain)
                            return False
                if "search_domains" in resolver:
                    if not isinstance(resolver["search_domains"], list):
                        self.lgr.error("search_domains must be a list")
                        return False
                    for domain in resolver["search_domains"]:
                        if not isinstance(domain, str):
                            self.lgr.error("Each search domain must be a"
                                           " string")
                            return False
                        if not search_pattern.fullmatch(domain):
                            self.lgr.error("invalid search domain %s",
                                           domain)
                            return False
                if "dnssec" in resolver:
                    if not isinstance(resolver["dnssec"], bool):
                        self.lgr.error("dnssec has to be bool")
                        return False
                if "networks" in resolver:
                    if not isinstance(resolver["networks"], list):
                        self.lgr.error("networks must be a list")
                        return False
                    for network in resolver["networks"]:
                        try:
                            ipaddress.ip_network(network)
                        except ValueError:
                            self.lgr.error("Network %s is not a valid "
                                           "network", network)
                            return False

                for key in resolver:
                    if key not in ["address", "protocol", "port",
                                   "name", "routing_domains",
                                   "search_domains", "dnssec",
                                   "networks"]:
                        self.lgr.error("Invalid property %s", key)
                        return False
                try:
                    ipaddress.ip_address(resolver["address"])
                except ValueError:
                    self.lgr.error("%s is not valid ip address",
                                   resolver["address"])
                    return False
            return True
        except AttributeError:
            self.lgr.error("Static servers must be list of"
                           " servers, invalid value %s was given", value)
            return False
