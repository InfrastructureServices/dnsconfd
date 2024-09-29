import socket
import ipaddress
from typing import Optional

from dnsconfd.network_objects import DnsProtocol


class ServerDescription:
    def __init__(self,
                 address_family: int,
                 address: bytes,
                 port: int = None,
                 sni: str = None,
                 priority: int = 100,
                 domains: list[tuple[str, bool]] = None,
                 interface: int = None,
                 protocol: DnsProtocol = DnsProtocol.PLAIN,
                 dnssec: bool = False):
        """ Object holding information about DNS server

        :param address_family: Indicates whether this is IPV4 of IPV6
        :type address_family: int
        :param address: Address of server
        :type address: bytes
        :param port: Port the server is listening on, defaults to None
        :type port: int, Optional
        :param sni: Server name indication, when TLS is used, defaults to None
        :type sni: str, Optional
        :param priority: Priority of this server. Higher priority means server
                         will be used instead of lower priority ones, defaults
                         to 50
        :type priority: int
        """
        self.address_family = address_family
        self.address = bytes(address)
        self.port = port
        self.sni = sni
        self.priority = priority
        self.domains = domains if domains is not None else [('.', False)]
        self.interface = interface
        self.protocol = protocol if protocol is not None else DnsProtocol.PLAIN
        self.dnssec = dnssec

    def to_unbound_string(self) -> str:
        """ Get string formatted in unbound format

        <address>[@port][#sni]

        :return: server string in unbound format
        :rtype: str
        """
        srv_string = socket.inet_ntop(self.address_family, self.address)
        if self.port:
            srv_string += f"@{self.port}"
        elif self.protocol == DnsProtocol.DNS_OVER_TLS:
            srv_string += "@853"
        if self.sni:
            srv_string += f"#{self.sni}"
        return srv_string

    @staticmethod
    def from_config(address: str,
                    protocol: DnsProtocol | None = None,
                    port: int | None = None,
                    sni: str | None = None,
                    domains: list[tuple[bool, str]] | None = None,
                    interface: int = None,
                    dnssec: bool = False) -> Optional["ServerDescription"]:
        """ Create instance of ServerDescription

        :param dnssec:
        :param interface:
        :param domains:
        :param address: String containing ip address
        :param protocol: Either 'plain' or 'DoT'
        :param port: port for connection
        :param sni: server name indication that should be presented in
                    certificate
        :return:
        """
        address_parsed = ipaddress.ip_address(address)
        if address_parsed.version == 4:
            address_family = socket.AF_INET
        else:
            address_family = socket.AF_INET6

        srv = ServerDescription(address_family,
                                socket.inet_pton(address_family,
                                                 str(address_parsed)),
                                port,
                                sni,
                                domains=domains,
                                interface=interface,
                                protocol=protocol,
                                dnssec=dnssec)
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
                    and self.sni == __value.sni
                    and self.protocol == __value.protocol
                    and self.priority == __value.priority
                    and self.dnssec == __value.dnssec
                    and self.interface == __value.interface
                    and self.domains == __value.domains)
        except AttributeError:
            return False

    def __str__(self) -> str:
        """ Get string with info about server

        :return: unbound formatted string
        :rtype: str
        """
        return self.to_unbound_string()

    def to_dict(self):
        if self.port:
            port = self.port
        elif self.protocol == DnsProtocol.DNS_OVER_TLS:
            port = 853
        else:
            port = 53
        domains = [a[0] for a in self.domains] if self.domains else None
        return {"address": self.get_server_string(),
                "port": port,
                "sni": self.sni,
                "domains": domains,
                "interface": self.interface,
                "protocol": self.protocol.name,
                "dnssec": self.dnssec}
