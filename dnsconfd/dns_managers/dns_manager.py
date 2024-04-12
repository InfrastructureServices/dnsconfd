from dnsconfd.network_objects import ServerDescription


class DnsManager:
    """ Parent class of objects that manage DNS caching services """

    """ Name of service this object manages """
    service_name = None

    def clear_state(self):
        """ Revert instance into state after initialization """
        raise NotImplementedError

    def update(self,
               zones_to_servers: dict[str, list[ServerDescription]]) -> bool:
        """ Update network_objects of a running service

        :param zones_to_servers: dict mapping zones to servers that should
                                 handle them
        :type zones_to_servers: dict[str, list[ServerDescription]]
        :return: True if update was successful, otherwise False
        :rtype: bool
        """
        raise NotImplementedError

    def get_status(self) -> dict[str, list[str]]:
        """ Get dict representing current network_objects of running service

        :return: dict representing current network_objects of running service
        :rtype: dict[str, list[str]]
        """
        raise NotImplementedError
