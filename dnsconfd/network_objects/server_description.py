import socket
from socket import AF_INET, AF_INET6
import ipaddress
from typing import Optional, Union
from urllib.parse import urlsplit, urlunsplit, parse_qs

import dbus

from dnsconfd.network_objects import DnsProtocol


class ServerDescription:
    def __init__(self,
                 address_family: int,
                 address: bytes,
                 port: int = None,
                 name: str = None,
                 priority: int = 100,
                 routing_domains: list[str] = None,
                 search_domains: list[str] = None,
                 interface: Optional[str] = None,
                 protocol: DnsProtocol = DnsProtocol.DNS_PLUS_UDP,
                 dnssec: bool = True,
                 networks: Union[list[ipaddress.IPv4Network],
                                 list[ipaddress.IPv6Network]] = None,
                 firewall_zone: str = None,
                 ca: str = None):
        """ Object holding information about DNS server

        :param address_family: Indicates whether this is IPV4 of IPV6
        :param address: Address of server
        :param port: Port the server is listening on, defaults to None
        :param name: Server name indication, when TLS is used, defaults to None
        :param priority: Priority of this server. Higher priority means server
                         will be used instead of lower priority ones, defaults
                         to 50
        :param routing_domains: domains whose members will be resolved only by
                                this or other servers with the same domain
                                entry
        :param search_domains: domains that should be used for host-name
                               lookup
        :param interface: indicating if server can be used only through
                          interface with this name
        :param protocol: protocol that should be used for communication with
                         this server
        :param dnssec: indicating whether this server supports dnssec or not
        :param networks: networks whose reverse dns records must be resolved
                         by this server
        :param firewall_zone: name of firewall zone that this server should be
                              associated with
        :param ca: Absolute path to certification authority bundle
        """
        self.address_family = address_family
        self.address = bytes(address)
        self.port = port
        self.name = name
        self.priority = priority
        self.networks = networks if networks else []
        if routing_domains:
            self.routing_domains = routing_domains
        else:
            self.routing_domains = ["."]
        self.search_domains = search_domains if search_domains else []
        self.interface = interface
        if protocol is not None:
            self.protocol = protocol
        else:
            self.protocol = DnsProtocol.DNS_PLUS_UDP
        self.dnssec = dnssec
        self.firewall_zone = firewall_zone
        self.ca = ca

    def to_unbound_string(self) -> str:
        """ Get string formatted in unbound format

        <address>[@port][#name]

        :return: server string in unbound format
        :rtype: str
        """
        srv_string = socket.inet_ntop(self.address_family, self.address)
        if self.port:
            srv_string += f"@{self.port}"
        elif self.protocol == DnsProtocol.DNS_PLUS_TLS:
            srv_string += "@853"
        if self.name:
            srv_string += f"#{self.name}"
        return srv_string

    @staticmethod
    def from_config(address: str,
                    protocol: Optional[DnsProtocol] = None,
                    port: Optional[int] = None,
                    name: Optional[str] = None,
                    routing_domains: Optional[list[str]] = None,
                    search_domains: Optional[list[str]] = None,
                    interface: Optional[str] = None,
                    dnssec: bool = False,
                    nets: Optional[list[str]] = None) -> Optional["ServerDescription"]:
        """ Create instance of ServerDescription

        :param address: String containing ip address
        :param protocol: Either 'plain' or 'DoT'
        :param port: Port for connection
        :param name: CN that should be presented in the server's certificate
        :param routing_domains: List of strings representing domains
                                forwarded to this server
        :param search_domains: List of strings representing search domains
                               that should be added to resolv.conf
        :param interface: Interface name when requests should be forwarded
                          through specific interface
        :param dnssec: Whether DNSSEC validation should pe performed on
                       responses from this server
        :param nets: Network ranges whose reverse ip records this server
                     can resolve
        :return: ServerDescription instance on success, otherwise None
        """
        address_parsed = ipaddress.ip_address(address)
        if address_parsed.version == 4:
            address_family = AF_INET
        else:
            address_family = AF_INET6

        networks = [ipaddress.ip_network(x) for x in nets] if nets else None

        srv = ServerDescription(address_family,
                                address_parsed.packed,
                                port,
                                name,
                                routing_domains=routing_domains,
                                search_domains=search_domains,
                                interface=interface,
                                protocol=protocol,
                                dnssec=dnssec,
                                networks=networks)
        return srv

    def get_server_string(self) -> str:
        """ Get string containing ip address

        :return: String containing ip address
        :rtype: str
        """
        return socket.inet_ntop(self.address_family, self.address)

    def __eq__(self, __value: object) -> bool:
        try:
            __value: ServerDescription
            return (self.address == __value.address
                    and self.port == __value.port
                    and self.name == __value.name
                    and self.protocol == __value.protocol
                    and self.priority == __value.priority
                    and self.dnssec == __value.dnssec
                    and self.interface == __value.interface
                    and self.routing_domains == __value.routing_domains
                    and self.search_domains == __value.search_domains
                    and self.networks == __value.networks)
        except AttributeError:
            return False

    def __str__(self) -> str:
        """ Get string with info about server

        :return: URI of server
        :rtype: str
        """
        return self.to_uri()

    def is_family(self, family: int) -> bool:
        """ Get whether this server is of specified IP family

        :param family: 4 or 6
        :return: True if this object is of the same family as specified,
                 otherwise False
        """
        if self.address_family == AF_INET and family == 4:
            return True
        return False

    def to_dict(self, strip: bool = False):
        """ Get dictionary representing values held by this object

        :param strip: Set if None values should be stripped
        :return: dictionary representation of this object
        """
        if self.port:
            port = self.port
        elif strip:
            port = None
        elif self.protocol == DnsProtocol.DNS_PLUS_TLS:
            port = 853
        else:
            port = 53
        result = {"address": self.get_server_string(),
                  "port": port,
                  "name": self.name,
                  "routing_domains": self.routing_domains,
                  "search_domains": self.search_domains,
                  "interface": self.interface,
                  "protocol": str(self.protocol),
                  "dnssec": self.dnssec,
                  "networks": [str(x) for x in self.networks],
                  "firewall_zone": self.firewall_zone}
        if strip:
            for key in list(result):
                if result[key] is None or result[key] == []:
                    result.pop(key)

        return result

    def get_rev_zones(self) -> list[str]:
        """ Get domains that this server should handle according to its
            networks

        :return: list of strings containing reverse domains belonging to
                 networks
        """
        zones = []
        for net in self.networks:
            mem_bits = 8 if net.version == 4 else 4
            to_whole = (mem_bits - (net.prefixlen % mem_bits)) % mem_bits
            subnets = list(net.subnets(to_whole))
            cut_index = ((subnets[0].max_prefixlen - subnets[0].prefixlen)
                         // mem_bits)

            for subnet in subnets:
                splitted = subnet.network_address.reverse_pointer.split(".")
                zones.append(".".join(splitted[cut_index:]))

        return zones

    def to_uri(self) -> str:
        ip_str = str(ipaddress.ip_address(self.address))
        if self.address_family == AF_INET:
            netloc = f"{ip_str}"
        else:
            netloc = f"[{ip_str}]"
        if self.port:
            netloc = f"{netloc}:{self.port}"

        return str(urlunsplit([str(self.protocol),
                               netloc,
                               "",
                               "",
                               self.name]))

    @staticmethod
    def from_dict(server: dict,
                  dnssec_enabled: bool = False) -> "ServerDescription":
        """ Construct ServerDescription instance from dictionary

        :param server: Dictionary holding servers attributes
        :param dnssec_enabled: Whether dnssec should be enabled
        :return: ServerDescription instance
        """
        if server.get("address", None) is None:
            raise ValueError("server has no address")
        try:
            if isinstance(server["address"], dbus.Array):
                converted_bytes = bytes(server["address"])
                parsed_address = ipaddress.ip_address(converted_bytes)
            else:
                parsed_address = ipaddress.ip_address(server["address"])
        except ValueError:
            raise ValueError("server has incorrect ip address "
                             f"{server['address']}")

        port = None
        if server.get("port", None) is not None:
            if (not isinstance(server["port"], int)
                    or not 0 < server["port"] < 65536):
                raise ValueError(f"server has bad port {server['port']}")
            port = int(server["port"])

        protocol = DnsProtocol.DNS_PLUS_UDP
        if server.get("protocol", None) is not None:
            if not isinstance(server["protocol"], str):
                raise ValueError("Protocol not a string")
            protocol = DnsProtocol.from_str(server["protocol"])
            if protocol is None:
                raise ValueError(f"unsupported protocol {server['protocol']}")

        name = None
        if server.get("name", None) is not None:
            if not isinstance(server["name"], str):
                raise ValueError("server name is not a string")
            name = str(server["name"])

        priority = 100
        if server.get("priority", None) is not None:
            if not isinstance(server["priority"], int):
                raise ValueError("priority is not an integer")
            priority = int(server["priority"])

        routing_domains = None
        if server.get("routing_domains", None) is not None:
            if not isinstance(server["routing_domains"], list):
                raise ValueError("Server routing domains is not list "
                                 f"{server['domains']}")
            for domain in server["routing_domains"]:
                if not isinstance(domain, str):
                    raise ValueError("server routing domain is not string")
            routing_domains = server["routing_domains"]

        search_domains = None
        if server.get("search_domains", None) is not None:
            if not isinstance(server["search_domains"], list):
                raise ValueError("Server search domains is not list "
                                 f"{server['domains']}")
            for domain in server["search_domains"]:
                if not isinstance(domain, str):
                    raise ValueError("Server search domain is not string")
            search_domains = server["search_domains"]

        interface = None
        if server.get("interface", None) is not None:
            if not isinstance(server["interface"], str):
                raise ValueError("Server has bad interface "
                                 f"{server['interface']}")
            interface = str(server["interface"])

        dnssec = True
        if server.get("dnssec", None) is not None:
            # here we have to check for dbus.Boolean as it does not
            # inherit from bool but from int
            if not isinstance(server["dnssec"], dbus.Boolean):
                raise ValueError("dnssec is not bool")
            dnssec = bool(server["dnssec"])

        if (dnssec_enabled and not dnssec
                and (not routing_domains
                     or [x for x in routing_domains if x == '.'])):
            raise ValueError("Server used for . domain can not have disabled "
                             "dnssec when it is enabled by configuration")

        networks = None
        if server.get("networks", None) is not None:
            if not isinstance(server["networks"], list):
                raise ValueError("Server networks is not "
                                 f"list {server['networks']}")
            networks = []
            for net in server["networks"]:
                try:
                    networks.append(ipaddress.ip_network(net))
                except ValueError:
                    raise ValueError("Server network is not "
                                     f"valid network {net}")

        firewall_zone = None
        if server.get("firewall_zone", None) is not None:
            if not isinstance(server["firewall_zone"], str):
                raise ValueError("Server search domain is not string")
            firewall_zone = str(server["firewall_zone"])

        ca = None
        if server.get("ca", None) is not None:
            if not isinstance(server["ca"], str):
                raise ValueError("servers CA is not a string")
            ca = str(server["ca"])

        # you may notice the type conversions throughout this method,
        # these are present to get rid of dbus types and prevent
        # unexpected problems in further processing

        addr_family = AF_INET if parsed_address.version == 4 else AF_INET6
        return ServerDescription(addr_family,
                                 parsed_address.packed,
                                 port,
                                 name,
                                 priority=priority,
                                 routing_domains=routing_domains,
                                 search_domains=search_domains,
                                 interface=interface,
                                 protocol=protocol,
                                 dnssec=dnssec,
                                 networks=networks,
                                 firewall_zone=firewall_zone,
                                 ca=ca)

    @staticmethod
    def from_uri(uri: str,
                 opt_search_domains: Optional[list[str]] = None
                 ) -> "ServerDescription":
        """ Create ServerDescription instance by parsing uri and options

        :raises: ValueError when unacceptable value is present
        :param uri: Uri describing DNS server
        :param opt_search_domains: list of search domains presented
        :return: ServerDescription instance
        """
        parsed_url = urlsplit(uri, scheme="dns+udp")
        protocol = DnsProtocol.from_str(parsed_url.scheme)
        if protocol is None:
            raise ValueError(f"Scheme {parsed_url.scheme} is not supported")

        if not parsed_url.hostname:
            raise ValueError("URI has to contain address")
        address_parsed = ipaddress.ip_address(parsed_url.hostname)
        address_family = AF_INET if address_parsed.version == 4 else AF_INET6

        parsed_qs = parse_qs(parsed_url.query)

        domains = {}
        for domain in parsed_qs.get("domain", []):
            domains[domain] = True

        domains = list(domains) if domains else None

        interface = None
        if parsed_qs.get("interface", None):
            interface = parsed_qs["interface"][-1]

        dnssec = True
        if parsed_qs.get("validation", False):
            dnssec = parsed_qs["validation"][-1] == "yes"

        networks = []
        for network in parsed_qs.get("network", []):
            try:
                networks.append(ipaddress.ip_network(network))
            except ValueError:
                raise ValueError(f"Specified invalid network {network}")

        name = parsed_url.fragment if parsed_url.fragment else None

        return ServerDescription(address_family,
                                 address_parsed.packed,
                                 parsed_url.port,
                                 name,
                                 routing_domains=domains,
                                 search_domains=opt_search_domains,
                                 interface=interface,
                                 protocol=protocol,
                                 dnssec=dnssec,
                                 networks=networks)
