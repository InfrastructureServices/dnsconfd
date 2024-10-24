import re
import socket
from logging.handlers import SysLogHandler

from dnsconfd.configuration import Option


class SyslogOption(Option):
    """
    Configuration option related to Syslog logging
    """
    network_re = r"(udp|tcp):(.+):([0-9]+)"

    def validate(self, value) -> bool:
        """ Validate that this value is a string specifying syslog destination
            or an empty string

        :param value: given value
        :return: True if value is valid otherwise False
        """
        if not value or (value.startswith("unix:") and len(value) > 5):
            return True
        match_object = re.fullmatch(self.network_re, value)
        if match_object is None:
            self.lgr.error("Bad syslog destination specification %s",
                           value)
            return False
        return True

    @staticmethod
    def parse_value(value: str) -> dict:
        """ Parse valid value for syslog_log option

        :param value: valid string value for this option
        :return: if unix domain is used then dict with "path" set,
                 otherwise dict with host, port and socket_type set
        """
        if value.startswith("unix:"):
            return {"path": value[5:]}
        match_object = re.fullmatch(SyslogOption.network_re, value)
        if match_object.group(1) == "udp":
            socket_type = socket.SOCK_DGRAM
        else:
            socket_type = socket.SOCK_STREAM
        host = match_object.group(2)
        if host.startswith("[") and host.endswith("]"):
            host = host[1:-1]
        port = int(match_object.group(3))
        return {"socket_type": socket_type, "host": host, "port": port}

    def construct_handler(self, value: str) -> SysLogHandler | None:
        """ Construct SysLog handler connected to specified destination

        :param value: string with specified syslog daemon destination
                      either unix:<path> or <transport_protocol>:<host>:<port>
                      where transport protocol is either tcp or udp, host
                      is ipv4, ipv6 in square brackets or hostname and port
                      number
        :return: SysLogHandler if destination can be connected, otherwise
                 None
        """
        parsed = self.parse_value(value)
        try:
            if "path" in parsed:
                return SysLogHandler(address=parsed["path"])
            else:
                return SysLogHandler(address=(parsed["host"], parsed["port"]),
                                     socktype=parsed["socket_type"])
        except OSError as e:
            self.lgr.error("Error while trying to connect to syslog %s",
                           e)
            return None
