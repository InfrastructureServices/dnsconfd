from dnsconfd.dns_managers import UnboundManager
from dnsconfd.network_objects import ServerDescription, DnsProtocol

import pytest
import socket


def create_instance():
    ins = UnboundManager({"dnssec_enabled": False,
                          "listen_address": "127.0.0.1",
                          "certification_authority": "whatever"})
    ins.lgr.disabled = True
    setattr(ins, "_executed_commands", [])

    def save_command(cmd):
        getattr(ins, "_executed_commands").append(cmd)
        return True

    ins._execute_cmd = save_command
    return ins


@pytest.fixture(scope="module")
def instance_one():
    return create_instance()


@pytest.mark.parametrize("zones_to_servers, commands", [
    ({".": [ServerDescription(socket.AF_INET,
                              bytes([192, 168, 9, 3]),
                              53,
                              "dummy.com")]},
     ["forward_add . 192.168.9.3@53#dummy.com",
      "flush_zone ."]),
    ({".": [ServerDescription(socket.AF_INET,
                              bytes([192, 168, 9, 3]),
                              53,
                              "dummy.com")],
      "dummy.com": [ServerDescription(socket.AF_INET,
                                      bytes([192, 168, 10, 3]),
                                      routing_domains=["dummy.com"],
                                      protocol=DnsProtocol.DNS_PLUS_TLS)]},
     ["forward_add +t dummy.com 192.168.10.3@853",
      "flush_zone dummy.com"]),
    ({".": [ServerDescription(socket.AF_INET,
                              bytes([192, 168, 9, 3]),
                              53,
                              "dummy.com")]},
     ["forward_remove +i dummy.com",
      "flush_zone dummy.com"]),
    ({},
     ["forward_add . 127.0.0.1",
      "flush_zone ."]),
    ({"dummy.com": [ServerDescription(socket.AF_INET,
                                      bytes([192, 168, 9, 3]),
                                      None,
                                      "dummy.com",
                                      routing_domains=["dummy.com"],
                                      protocol=DnsProtocol.DNS_PLUS_TLS)]},
     ["forward_add +t dummy.com 192.168.9.3@853#dummy.com",
      "flush_zone dummy.com"]),
    ({"dummy.com": [ServerDescription(socket.AF_INET,
                                      bytes([192, 168, 9, 3]),
                                      None,
                                      routing_domains=["dummy.com"])]},
     ["forward_remove +i dummy.com",
      "forward_add dummy.com 192.168.9.3",
      "flush_zone dummy.com"])
])
def test_first_update(zones_to_servers, commands, instance_one):
    getattr(instance_one, "_executed_commands").clear()
    instance_one.update(zones_to_servers)
    assert getattr(instance_one, "_executed_commands") == commands
