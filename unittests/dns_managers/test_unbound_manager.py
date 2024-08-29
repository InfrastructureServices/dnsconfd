from dnsconfd.dns_managers import UnboundManager
from dnsconfd.network_objects import ServerDescription, DnsProtocol

import pytest
import socket


@pytest.fixture(scope="module")
def instance():
    ins = UnboundManager()
    ins.lgr.disabled = True
    setattr(ins, "_executed_commands", [])

    def save_command(cmd):
        getattr(ins, "_executed_commands").append(cmd)
        return True

    ins._execute_cmd = save_command
    return ins


@pytest.mark.parametrize("zones_to_servers, commands", [
    ({".": [ServerDescription(socket.AF_INET,
                              bytes([192, 168, 9, 3]),
                              53,
                              "dummy.com")]},
     ["flush_zone .",
      "forward_add . 192.168.9.3@53#dummy.com"]),
    ({".": [ServerDescription(socket.AF_INET,
                              bytes([192, 168, 9, 3]),
                              53,
                              "dummy.com")],
      "dummy.com": [ServerDescription(socket.AF_INET,
                                      bytes([192, 168, 10, 3]),
                                      domains=[("dummy.com", True)],
                                      protocol=DnsProtocol.DNS_OVER_TLS)]},
     ["flush_zone dummy.com",
      "forward_add +t dummy.com 192.168.10.3@853"]),
    ({".": [ServerDescription(socket.AF_INET,
                              bytes([192, 168, 9, 3]),
                              53,
                              "dummy.com")]},
     ["forward_remove dummy.com",
      "flush_zone dummy.com"])
])
def test_first_update(zones_to_servers, commands, instance):
    getattr(instance, "_executed_commands").clear()
    instance.update({".": [ServerDescription(socket.AF_INET,
                                             bytes([192, 168, 9, 3]),
                                             53,
                                             "dummy.com")]
                     })
    instance.update(zones_to_servers)
    assert getattr(instance, "_executed_commands") == commands
