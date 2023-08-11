class ServerDescription:
    def __init__(self, address, port=53, sni=None, address_family=2, priority = 50):
        self.address_family = address_family
        self.address = address
        self.port = port
        self.sni = sni
        self.priority = priority

    def to_unbound_string(self) -> str:
        srv_string = ""
        if self.address_family == 2:
            srv_string += ".".join([str(int(num)) for num in self.address])
        else:
            temp_string = [hex(int(num))[2:] for num in self.address]
            for ind in range(0, len(temp_string) - 1, 2):
                srv_string += temp_string[ind] + temp_string[ind+1] + ":"
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
