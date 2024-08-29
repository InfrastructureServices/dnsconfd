from dnsconfd.configuration import StringOption

import pytest


@pytest.fixture
def instance():
    ins = StringOption("test",
                       "test",
                       "whatever",
                       validation=r"text[0-9]*")
    ins.lgr.disabled = True
    return ins


@pytest.mark.parametrize("value, result", [
    ("text", True),
    ("text1", True),
    ("text12", True),
    ("texts", False)
])
def test_validate(value, result, instance):
    assert instance.validate(value) == result
