import ipaddress

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
        if not isinstance(value, list):
            self.lgr.error("static_servers is not a list")
            return False
        for server in value:
            if (self._is_address_bad(server)
                    or self._is_protocol_bad(server)
                    or self._is_port_bad(server)
                    or self._is_name_bad(server)
                    or self._is_routing_domains_bad(server)
                    or self._is_search_domains_bad(server)
                    or self._is_dnssec_bad(server)
                    or self._is_networks_bad(server)
                    or self._are_keys_bad(server)):
                return False
        return True

    def _is_address_bad(self, server) -> bool:
        if "address" not in server:
            self.lgr.error("missing resolver address "
                           "specification")
            return True
        try:
            ipaddress.ip_address(server["address"])
        except ValueError:
            self.lgr.error("%s is not valid ip address",
                           server["address"])
            return True
        return False

    def _is_protocol_bad(self, server) -> bool:
        if "protocol" in server:
            if not isinstance(server["protocol"], str):
                self.lgr.error("protocol has to be a string")
                return True
            if (server["protocol"].lower() != "dot"
                    and server["protocol"].lower() != "plain"):
                self.lgr.error("protocol contains invalid value")
                return True
        return False

    def _is_port_bad(self, server) -> bool:
        if "port" in server:
            if not isinstance(server["port"], int):
                self.lgr.error("port has to be number")
                return True
            if server["port"] < 1 or server["port"] > 65535:
                self.lgr.error("invalid port number")
                return True
        return False

    def _is_name_bad(self, server) -> bool:
        if "name" in server:
            if not isinstance(server["name"], str):
                self.lgr.error("invalid name")
                return True
        return False

    def _is_routing_domains_bad(self, server) -> bool:
        if "routing_domains" in server:
            if not isinstance(server["routing_domains"], list):
                self.lgr.error("routing_domains must be a list")
                return True
            for domain in server["routing_domains"]:
                if not isinstance(domain, str):
                    self.lgr.error("Each routing domain must be a"
                                   " string")
                    return True
        return False

    def _is_search_domains_bad(self, server) -> bool:
        if "search_domains" in server:
            if not isinstance(server["search_domains"], list):
                self.lgr.error("search_domains must be a list")
                return True
            for domain in server["search_domains"]:
                if not isinstance(domain, str):
                    self.lgr.error("Each search domain must be a"
                                   " string")
                    return True
                if domain == ".":
                    self.lgr.error("Search domain can not be '.'")
                    return True
        return False

    def _is_dnssec_bad(self, server) -> bool:
        if "dnssec" in server:
            if not isinstance(server["dnssec"], bool):
                self.lgr.error("dnssec has to be bool")
                return True
        return False

    def _is_networks_bad(self, server) -> bool:
        if "networks" in server:
            if not isinstance(server["networks"], list):
                self.lgr.error("networks must be a list")
                return True
            for network in server["networks"]:
                try:
                    ipaddress.ip_network(network)
                except ValueError:
                    self.lgr.error("Network %s is not a valid "
                                   "network", network)
                    return True
        return False

    def _are_keys_bad(self, keys) -> bool:
        for key in keys:
            if key not in ["address", "protocol", "port",
                           "name", "routing_domains",
                           "search_domains", "dnssec",
                           "networks"]:
                self.lgr.error("Invalid property %s", key)
                return True
        return False
