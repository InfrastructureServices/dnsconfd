import socket
import os.path

class InterfaceConfiguration:
    """ Object holding configuration of interface as systemd-resolved would describe it
        
    :param domains: Domains that the interface should handle, defaults to []
    :type domains: list, optional
    :param servers: Servers to which the interface should forward queries to, defaults to []
    :type servers: list, optional
    :param dns_over_tls: Indicates whether the interface should use DNS over TLS,
                            defaults to False
    :type dns_over_tls: bool, optional
    :param dnssec: Indicates whether the interface should use DNSSEC, defaults to False
    :type dnssec: bool, optional
    :param is_default: Indicates whether the interface should be used as default
                        (Highest priority), defaults to False
    :type is_default: bool, optional
    """
    def __init__(self, interface_index: int, domains: list[tuple[str, bool]] = [], servers = [],
                 dns_over_tls = False, dnssec = False, is_default = False):
        self.domains = domains
        self.servers = servers
        self.dns_over_tls = dns_over_tls
        self.dnssec = dnssec
        self.is_default = is_default
        self.interface_index = interface_index
        self.finished = False

    def __str__(self) -> str:
        """ Create string representation of instance

        This makes the logs more readable

        :return: String representation of this instance
        :rtype: str
        """
        ifname = self.get_ifname()
        domains_str = ' '.join([domain for (domain, is_routing) in self.domains])
        servers_str = ' '.join([str(server) for server in self.servers])
        description = f"{{iface {ifname} (#{self.interface_index}), domains: {domains_str}, servers: {servers_str}, "
        description += f"is_default: {self.is_default}}}"
        return  description

    def is_interface_wireless(self) -> bool:
        """ Get whether the interface that this instance represents is wireless or not

        :return: True if interface is wireless, otherwise False
        :rtype: bool
        """
        try:
            name = socket.if_indextoname(self.interface_index)
            return os.path.isdir(f"/sys/class/net/{name}/wireless")
        except OSError:
            return False

    def get_ifname(self) -> str:
        """ Get interface name

        :return: Name of the interface represented by this instance, if socket is unable
                 to translate it, then string of index will be returned
        :rtype: str
        """
        try:
            return socket.if_indextoname(self.interface_index)
        except OSError as e:
            return str(self.interface_index)
