from dnsconfd.configuration import IpOption

import pytest


@pytest.fixture
def instance():
    ins = IpOption("test", "test", True)
    ins.lgr.disabled = True
    return ins


@pytest.mark.parametrize("value, result", [
    ("127.0.0.1", True),
    ("whatever.1.1.1", False),
    ("::1", True),
    ("300.0.0.1", False),
    (" ", False),
    ("2001:0000:130F:0000:0000:09C0:876A:130B", True)
])
def test_validate(value, result, instance):
    assert instance.validate(value) == result
