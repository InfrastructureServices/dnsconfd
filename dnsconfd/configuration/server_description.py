import socket

class ServerDescription:
    def __init__(self, address, port=53, sni=None, address_family=2, priority = 50):
        self.address_family = address_family
        self.address = address
        self.port = port
        self.sni = sni
        self.priority = priority

    def to_unbound_string(self) -> str:
        srv_string = socket.inet_ntop(self.address_family, self.address)
        if self.port:
            srv_string += f"@{self.port}"
        if self.sni:
            srv_string += f"#{self.sni}"
        return srv_string

    def __eq__(self, __value: object) -> bool:
        try:
            return (self.address == __value.address
                    and self.port == __value.port
                    and self.sni == __value.sni)
        except AttributeError:
            return False

    def __str__(self) -> str:
        return self.to_unbound_string()
