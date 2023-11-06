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

    l4 = configuration.ServerDescription(BIN_LOCALHOST4, address_family=int(socket.AF_INET))
    assert(l4.to_unbound_string() == LOCALHOST4+'@53')

    l6 = configuration.ServerDescription(BIN_LOCALHOST6, address_family=int(socket.AF_INET6))
    assert(l6.to_unbound_string() == LOCALHOST6+'@53')

    ls4 = configuration.ServerDescription(BIN_LOCALHOST4, port=853, sni='server.test', address_family=int(socket.AF_INET))
    assert(ls4.to_unbound_string() == LOCALHOST4+'@853#server.test')
