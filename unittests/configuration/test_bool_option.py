from dnsconfd.configuration import BoolOption

import pytest


@pytest.fixture
def instance():
    ins = BoolOption("test", "test", True)
    ins.lgr.disabled = True
    return ins


@pytest.mark.parametrize("value, result", [
    ("Hello", False),
    (True, True),
    (False, True)
])
def test_validate(value, result, instance):
    assert instance.validate(value) == result
