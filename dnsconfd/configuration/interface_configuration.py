import socket
import os


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
    def __init__(self, interface_index: int, domains = [], servers = [], dns_over_tls = False, dnssec = False, is_default = False):
        self.domains = domains
        self.servers = servers
        self.dns_over_tls = dns_over_tls
        self.dnssec = dnssec
        self.is_default = is_default
        self._interface_index = interface_index

    def __str__(self) -> str:
        """ Create string representation of instance

        This makes the logs more readable

        :return: String representation of this instance
        :rtype: str
        """
        description = f"{{index {self._interface_index}, domains: {self.domains}, servers: {self.servers}, "
        description += f"is_default: {self.is_default}}}"
        return  description

    def isInterfaceWireless(self):
        name = socket.if_indextoname(self._interface_index)
        try:
            return os.isdir(f"/sys/class/net/{name}/wireless")
        except OSError:
            return False
