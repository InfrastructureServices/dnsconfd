import socket

from dnsconfd.configuration import SyslogOption

import pytest


@pytest.fixture
def instance():
    ins = SyslogOption("test",
                       "test",
                       "whatever")
    ins.lgr.disabled = True
    return ins


@pytest.mark.parametrize("value, result", [
    ("unix:/dev/log", True),
    ("udp:localhost:514", True),
    ("udp:[::1]:514", True),
    ("tcp:127.0.0.1:514", True),
    ("tcp:host.example.com:514", True),
    ("tcp:host.example.com:", False),
    ("garbage", False),
    ("unix:", False),
    ("tcp::514", False),
])
def test_validate(value, result, instance):
    assert instance.validate(value) == result


@pytest.mark.parametrize("value, result", [
    ("unix:/dev/log", {"path": "/dev/log"}),
    ("udp:localhost:514", {"socket_type": socket.SOCK_DGRAM,
                           "host": "localhost", "port": 514}),
    ("udp:[::1]:514", {"socket_type": socket.SOCK_DGRAM,
                       "host": "::1", "port": 514}),
    ("tcp:127.0.0.1:514", {"socket_type": socket.SOCK_STREAM,
                           "host": "127.0.0.1", "port": 514}),
    ("tcp:host.example.com:514", {"socket_type": socket.SOCK_STREAM,
                                  "host": "host.example.com", "port": 514}),
])
def test_parse_value(value, result, instance):
    assert instance.parse_value(value) == result
