from dnsconfd.configuration import StaticServersOption

import pytest


@pytest.fixture
def instance():
    ins = StaticServersOption("test", "test", [])
    # ins.lgr.disabled = True
    return ins


@pytest.mark.parametrize("value, result", [
    ([{"address": "192.168.8.3"}],
     True),
    ([{"address": "192.168.8"}],
     False),
    ([{"address": "192.168.8.3"},
      {"address": "192.168.9.3", "protocol": "DoT"}],
     True),
    ([{"address": "192.168.8.3"},
      {"address": "192.168.9.3", "protocol": "garbage"}],
     False),
    ([{"address": "192.168.8.3"},
      {"address": "192.168.9.3", "protocol": "plain", "routing_domains": ["dummy.com"]}],
     True),
    ([{"address": "192.168.8.3"},
      {"address": "192.168.9.3", "protocol": "plain", "domains": [False]}],
     False),
])
def test_validate(value, result, instance):
    assert instance.validate(value) == result
