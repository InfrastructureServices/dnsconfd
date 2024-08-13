import socket
import os.path
from dnsconfd.network_objects import ServerDescription


class InterfaceConfiguration:
    def __init__(self,
                 interface_index: int,
                 domains: list[tuple[str, bool]] = None,
                 servers: list[ServerDescription] = None,
                 dns_over_tls: bool = False,
                 dnssec: bool = False,
                 is_default: bool = None):
        """ Object holding network_objects of interface as systemd-resolved
        would describe it

        :param interface_index: Index of interface as kernel sees it
        :type interface_index: int
        :param domains: Domains that the interface should handle,
                        defaults to []
        :type domains: list[tuple[str, bool]], optional
        :param servers: Servers to which the interface should forward queries
                        to, defaults to []
        :type servers: list[ServerDescription], optional
        :param dns_over_tls: Indicates whether the interface should use
                             DNS over TLS, defaults to False
        :type dns_over_tls: bool, optional
        :param dnssec: Indicates whether the interface should use DNSSEC,
                       defaults to False
        :type dnssec: bool, optional
        :param is_default: Indicates whether the interface should be used as
                           default (Highest priority), defaults to False
        :type is_default: bool, optional
        """
        self.domains: list[tuple[str, bool]] = domains
        self.servers: list[ServerDescription] = servers
        self.dns_over_tls: bool = dns_over_tls
        self.dnssec: bool = dnssec
        self.is_default: bool = is_default
        self.interface_index: int = interface_index

    def is_ready(self) -> bool:
        """ Get whether this interface is ready for insertion into cache
            network_objects

        :return: True if interface is ready, otherwise False
        :rtype: bool
        """
        return (self.domains is not None
                and self.servers is not None
                and self.is_default is not None)

    def __str__(self) -> str:
        """ Create string representation of instance

        This makes the logs more readable

        :return: String representation of this instance
        :rtype: str
        """
        domains_str = ' '.join([domain for (domain, _) in self.domains])
        servers_str = ' '.join([str(server) for server in self.servers])
        return (f"iface {self.get_if_name()} "
                + f"(#{self.interface_index}), domains: {domains_str}, "
                + f"servers: {servers_str}, "
                + f"is_default: {self.is_default}")

    def is_interface_wireless(self) -> bool:
        """ Get whether this interface is wireless or not

        :return: True if interface is wireless, otherwise False
        :rtype: bool
        """
        try:
            name = socket.if_indextoname(self.interface_index)
            return os.path.isdir(f"/sys/class/net/{name}/wireless")
        except OSError:
            return False

    def get_if_name(self, strict=False) -> str | None:
        """ Get interface name

        :return: Name of the interface, if socket is unable
                 to translate it, then string of index will be returned
        :rtype: str | None
        """
        try:
            return socket.if_indextoname(self.interface_index)
        except OSError:
            return str(self.interface_index) if not strict else None

    def to_dict(self) -> dict:
        """ Get dictionary containing all information about interface

        :return: dictionary containing all information
        :rtype: dict
        """
        return {"domains": self.domains,
                "servers": [str(a) for a in self.servers],
                "dns_over_tls": self.dns_over_tls,
                "dnssec": self.dnssec,
                "is_default": self.is_default,
                "interface_name": self.get_if_name()}
