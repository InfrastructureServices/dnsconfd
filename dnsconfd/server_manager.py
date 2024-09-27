import logging

from dnsconfd.network_objects import ServerDescription, DnsProtocol


class ServerManager:
    def __init__(self, config: dict):
        self.lgr = logging.getLogger(self.__class__.__name__)
        self.dynamic_servers: list[ServerDescription] = []
        self.static_servers: list[ServerDescription] = []

        for resolver in config["static_servers"]:
            prot = resolver.get("protocol", None)
            if prot is not None:
                if prot == "plain":
                    prot = DnsProtocol.PLAIN
                elif prot == "DoT":
                    prot = DnsProtocol.DNS_OVER_TLS
            port = resolver.get("port", None)
            sni = resolver.get("sni", None)
            domains = resolver.get("domains", None)
            if domains is not None:
                transformed_domains = []
                for x in domains:
                    transformed_domains.append((x["domain"], x["search"]))
                domains = transformed_domains
            interface = resolver.get("interface", None)
            dnssec = resolver.get("dnssec", False)

            new_srv = ServerDescription.from_config(resolver["address"],
                                                    prot,
                                                    port,
                                                    sni,
                                                    domains,
                                                    interface,
                                                    dnssec)
            new_srv.priority = 150
            self.static_servers.append(new_srv)
        if self.static_servers:
            self.lgr.info(f"Configured static servers: {self.static_servers}")

    def get_zones_to_servers(self):
        new_zones_to_servers = {}

        search_domains = []

        for server in self.dynamic_servers + self.static_servers:
            for domain, search in server.domains:
                try:
                    new_zones_to_servers[domain].append(server)
                except KeyError:
                    new_zones_to_servers[domain] = [server]
                if search:
                    search_domains.append(domain)

        for zone in new_zones_to_servers:
            new_zones_to_servers[zone].sort(key=lambda x: x.priority,
                                            reverse=True)
        self.lgr.debug(f"New zones to server prepared: {new_zones_to_servers}")
        self.lgr.debug(f"New search domains prepared: {search_domains}")
        return new_zones_to_servers, search_domains

    def get_all_servers(self):
        return self.dynamic_servers + self.static_servers

    def set_dynamic_servers(self, servers: list[ServerDescription]):
        self.dynamic_servers = servers

    def get_all_interfaces(self):
        found_interfaces = []

        for server in self.dynamic_servers + self.static_servers:
            if (server.interface is not None
                    and server.interface not in found_interfaces):
                found_interfaces.append(server.interface)
        return found_interfaces
