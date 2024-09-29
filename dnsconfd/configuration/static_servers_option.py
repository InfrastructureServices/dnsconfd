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
        domain_pattern = re.compile(domain_re)
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
                if "sni" in resolver:
                    if not isinstance(resolver["sni"], str):
                        self.lgr.error("invalid sni")
                        return False
                if "domains" in resolver:
                    if not isinstance(resolver["domains"], list):
                        self.lgr.error("domains must be a list")
                        return False
                    for domain in resolver["domains"]:
                        if not isinstance(domain["domain"], str):
                            self.lgr.error("each domain must be a string")
                            return False
                        if not isinstance(domain["search"], bool):
                            self.lgr.error("search has to be bool")
                            return False
                        if not domain_pattern.fullmatch(domain["domain"]):
                            self.lgr.error("invalid domain %s",
                                           domain['domain'])
                            return False
                if "dnssec" in resolver:
                    if not isinstance(resolver["dnssec"], bool):
                        self.lgr.error("dnssec has to be bool")
                        return False
                for key in resolver:
                    if key not in ["address", "protocol", "port",
                                   "sni", "domains", "dnssec"]:
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
