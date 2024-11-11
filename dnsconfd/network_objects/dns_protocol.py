from enum import Enum
from typing import Optional


class DnsProtocol(Enum):
    """ Dns communication protocols """
    DNS_PLUS_UDP = 0
    DNS_PLUS_TCP = 1
    DNS_PLUS_TLS = 2

    def __str__(self):
        protocol_to_str = {DnsProtocol.DNS_PLUS_UDP: "dns+udp",
                           DnsProtocol.DNS_PLUS_TCP: "dns+tcp",
                           DnsProtocol.DNS_PLUS_TLS: "dns+tls"}
        return protocol_to_str[self]

    @staticmethod
    def from_str(name: str) -> Optional["DnsProtocol"]:
        str_to_protocol = {"dns+udp": DnsProtocol.DNS_PLUS_UDP,
                           "dns+tcp": DnsProtocol.DNS_PLUS_TCP,
                           "dns+tls": DnsProtocol.DNS_PLUS_TLS}
        return str_to_protocol.get(name.lower(), None)
