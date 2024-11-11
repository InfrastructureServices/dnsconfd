import logging

from dnsconfd.network_objects import ServerDescription, DnsProtocol
from dnsconfd.input_modules import ResolvingMode


class ServerManager:
    def __init__(self, config: dict):
        """ Manager of server information

        :param config: dictionary with configuration
        """
        self.lgr = logging.getLogger(self.__class__.__name__)
        self.dynamic_servers: list[ServerDescription] = []
        self.static_servers: list[ServerDescription] = []

        self.mode = ResolvingMode.FREE

        for resolver in config["static_servers"]:
            prot = resolver.get("protocol", None)
            if prot is not None:
                prot = DnsProtocol.from_str(resolver["protocol"].lower())
            port = resolver.get("port", None)
            name = resolver.get("name", None)
            routing_domains = resolver.get("routing_domains", None)
            search_domains = resolver.get("search_domains", None)
            interface = resolver.get("interface", None)
            dnssec = resolver.get("dnssec", False)

            new_srv = ServerDescription.from_config(resolver["address"],
                                                    prot,
                                                    port,
                                                    name,
                                                    routing_domains,
                                                    search_domains,
                                                    interface,
                                                    dnssec)
            new_srv.priority = 150
            self.static_servers.append(new_srv)
        if self.static_servers:
            self.lgr.info("Configured static servers: %s",
                          self.static_servers)

    def get_zones_to_servers(self, servers) \
            -> tuple[dict[str, list[ServerDescription]], list[str]]:
        """ Get zones to servers and search domains

        :return: tuple with zones to servers dictionary and list of
        search domains
        """
        new_zones_to_servers = {}

        search_domains = {}

        for server in servers:
            if (server.interface is not None
                    and self.mode == ResolvingMode.FULL_RESTRICTIVE):
                continue
            for domain in server.routing_domains:
                if server.interface is not None:
                    if (self.mode == ResolvingMode.RESTRICT_GLOBAL
                            and domain == "."):
                        continue
                new_zones_to_servers.setdefault(domain, []).append(server)

            for rev_zone in server.get_rev_zones():
                new_zones_to_servers.setdefault(rev_zone, []).append(server)

            for domain in server.search_domains:
                search_domains[domain] = True

        for zone in new_zones_to_servers.values():
            zone.sort(key=lambda x: x.priority, reverse=True)
        self.lgr.debug("New zones to server prepared: %s",
                       new_zones_to_servers)
        self.lgr.debug("New search domains prepared: %s",
                       search_domains.keys())
        return new_zones_to_servers, list(search_domains.keys())

    def get_all_servers(self) -> list[ServerDescription]:
        """ Get all forwarders

        :return: list of server descriptions for all forwarders
        """
        return self.dynamic_servers + self.static_servers

    def get_used_servers(self) -> list[ServerDescription]:
        """ Get forwarders that will be used according to mode

        :return: list of server descriptions of forwarders that will be used
        """
        all_servers = self.dynamic_servers + self.static_servers
        used_servers = []
        for server in all_servers:
            if server.interface is not None:
                if self.mode == ResolvingMode.FULL_RESTRICTIVE:
                    continue
                elif self.mode == ResolvingMode.RESTRICT_GLOBAL:
                    # if domains contain only . then omit this server
                    subdomain_present = False
                    for domain in server.routing_domains:
                        if domain != ".":
                            subdomain_present = True
                            break
                    if (not subdomain_present
                            and not server.networks
                            and not server.search_domains):
                        continue
            used_servers.append(server)

        return used_servers

    def set_dynamic_servers(self, servers: list[ServerDescription], mode: int):
        """ Set list of dynamic servers

        :param servers: list of new dynamic servers
        :param mode: Resolving mode representing how the servers should be
                     handled
        """
        self.dynamic_servers = servers
        self.mode = mode
