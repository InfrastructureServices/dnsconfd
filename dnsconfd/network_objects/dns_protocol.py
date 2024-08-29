from enum import Enum


class DnsProtocol(Enum):
    """ Dns communication protocols """
    PLAIN = 0
    DNS_OVER_TLS = 1
