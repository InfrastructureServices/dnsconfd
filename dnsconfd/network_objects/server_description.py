import socket


class ServerDescription:
    def __init__(self,
                 address_family: bytes,
                 address: bytes,
                 port: int = None,
                 sni: str = None,
                 priority: int = 50):
        """ Object holding information about DNS server

        :param address_family: Bytes indicating whether this is IPV4 of IPV6
        :type address_family: bytes
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
        self.tls = False

    def to_unbound_string(self) -> str:
        """ Get string formatted in unbound format

        <address>[@port][#sni]

        :return: server string in unbound format
        :rtype: str
        """
        srv_string = socket.inet_ntop(self.address_family, self.address)
        if self.port:
            srv_string += f"@{self.port}"
        elif self.tls:
            srv_string += "@853"
        if self.sni:
            srv_string += f"#{self.sni}"
        return srv_string

    def __eq__(self, __value: object) -> bool:
        try:
            __value: ServerDescription
            return (self.address == __value.address
                    and self.port == __value.port
                    and self.sni == __value.sni
                    and self.tls == __value.tls
                    and self.priority == __value.priority)
        except AttributeError:
            return False

    def __str__(self) -> str:
        """ Get string with info about server

        :return: unbound formatted string
        :rtype: str
        """
        return self.to_unbound_string()
