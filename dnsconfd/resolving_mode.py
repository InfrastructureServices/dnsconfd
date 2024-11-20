from enum import Enum


class ResolvingMode(Enum):
    """ Resolving mode which determines how the received servers
    should be used
    """
    BACKUP = 0  # use interface servers for resolving of everything
    PREFER = 1
    # only global servers can resolve '.', interface
    # servers can resolve only subdomains
    EXCLUSIVE = 2  # only global servers can be used for resolving

    def __str__(self):
        mode_to_str = {
            ResolvingMode.BACKUP: "backup",
            ResolvingMode.PREFER: "prefer",
            ResolvingMode.EXCLUSIVE: "exclusive"
        }
        return mode_to_str[self]
