from dnsconfd.configuration import ServerDescription

class InterfaceConfiguration:
    def __init__(self):
        self.domains: list[str] = []
        self.servers: list[ServerDescription] = []
        self.dns_over_tls = False
        self.dnssec = True
        self.is_default = False

    def __str__(self) -> str:
        description = f"{{domains: {self.domains}, servers: {self.servers}, "
        description += f"is_default: {self.is_default}}}"
        return  description
