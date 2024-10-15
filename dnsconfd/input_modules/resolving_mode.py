from enum import Enum


class ResolvingMode(Enum):
    """ Resolving mode which determines how the received servers
    should be used
    """
    FREE = 0  # use interface servers for resolving of everything
    RESTRICT_GLOBAL = 1
    # only global servers can resolve '.', interface
    # servers can resolve only subdomains
    FULL_RESTRICTIVE = 2  # only global servers can be used for resolving
