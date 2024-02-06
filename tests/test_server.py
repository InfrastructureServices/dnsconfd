#!/usr/bin/python
#
# 
import socket
import sys
import os.path
import pytest

sys.path.append(os.path.join(sys.path[0], '..'))

from dnsconfd import configuration


def test_server_description():
    LOCALHOST4 = '127.0.0.1'
    LOCALHOST6 = '::1'
    BIN_LOCALHOST4 = socket.inet_pton(socket.AF_INET, LOCALHOST4)
    BIN_LOCALHOST6 = socket.inet_pton(socket.AF_INET6, LOCALHOST6)

    l4 = configuration.ServerDescription(socket.AF_INET, BIN_LOCALHOST4)
    assert(l4.to_unbound_string() == LOCALHOST4)

    l6 = configuration.ServerDescription(socket.AF_INET6, BIN_LOCALHOST6)
    assert(l6.to_unbound_string() == LOCALHOST6)

    ls4 = configuration.ServerDescription(socket.AF_INET, BIN_LOCALHOST4, port=853, sni='server.test')
    assert(ls4.to_unbound_string() == LOCALHOST4+'@853#server.test')
