from dnsconfd.configuration import DnsconfdArgumentParser

import pytest
from io import StringIO


def config_file_stream(path):
    return StringIO("")


@pytest.fixture
def empty_conf_instance():
    ins = DnsconfdArgumentParser()
    ins.lgr.disabled = True
    ins._config_log = lambda x: None
    ins._open_config_file = config_file_stream
    ins._env = {}
    ins.add_commands()
    ins.add_arguments()
    return ins


def filled_config_file_stream(path):
    return StringIO("ignore_api: yes\nlisten_address: 127.0.0.2\n")


@pytest.fixture
def filled_conf_instance():
    ins = DnsconfdArgumentParser()
    ins.lgr.disabled = True
    ins._config_log = lambda x: None
    ins._open_config_file = filled_config_file_stream
    ins._env = {"LISTEN_ADDRESS": "127.0.0.3", "DNSSEC_ENABLED": "1"}
    ins.add_commands()
    ins.add_arguments()
    return ins


@pytest.mark.parametrize("args, raised_exception, parsed", [
    (["--log-level", "DEBUG"], None, {'log_level': 'DEBUG',
                                      'file_log': '',
                                      'journal_log': False,
                                      'stderr_log': True,
                                      'syslog_log': '',
                                      'dbus_name': 'com.redhat.dnsconfd',
                                      'resolv_conf_path': '/etc/resolv.conf',
                                      'listen_address': '127.0.0.1',
                                      'prioritize_wire': True,
                                      'resolver_options': 'edns0 trust-ad',
                                      'dnssec_enabled': False,
                                      'handle_routing': False,
                                      'config_file': '/etc/dnsconfd.conf',
                                      'api_choice': 'dnsconfd',
                                      'certification_authority': '/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem',
                                      'static_servers': [],
                                      'ignore_api': False}),
    (["--log-level", "DEB"], ValueError, {}),
    (["--listen-address", "nonsense"], ValueError, {})
])
def test_parse(args, raised_exception, parsed, empty_conf_instance):
    if raised_exception is not None:
        with pytest.raises(raised_exception):
            empty_conf_instance.parse_args(args)
    else:
        output = vars(empty_conf_instance.parse_args(args))
        # we will not be checking func, it is a helper variable
        output.pop("func")
        assert output == parsed


@pytest.mark.parametrize("args, raised_exception, parsed", [
    (["--log-level", "ERROR"],
     None,
     {'log_level': 'ERROR',
      'file_log': '',
      'journal_log': False,
      'stderr_log': True,
      'syslog_log': '',
      'dbus_name': 'com.redhat.dnsconfd',
      'resolv_conf_path': '/etc/resolv.conf',
      'listen_address': '127.0.0.3',
      'prioritize_wire': True,
      'resolver_options': 'edns0 trust-ad',
      'dnssec_enabled': True,
      'handle_routing': False,
      'config_file': '/etc/dnsconfd.conf',
      'api_choice': 'dnsconfd',
      'certification_authority': '/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem',
      'static_servers': [],
      'ignore_api': True}),
    (["--listen-address", "127.0.0.4"],
     None,
     {'log_level': 'INFO',
      'file_log': '',
      'journal_log': False,
      'stderr_log': True,
      'syslog_log': '',
      'dbus_name': 'com.redhat.dnsconfd',
      'resolv_conf_path': '/etc/resolv.conf',
      'listen_address': '127.0.0.4',
      'prioritize_wire': True,
      'resolver_options': 'edns0 trust-ad',
      'dnssec_enabled': True,
      'handle_routing': False,
      'config_file': '/etc/dnsconfd.conf',
      'api_choice': 'dnsconfd',
      'certification_authority': '/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem',
      'static_servers': [],
      'ignore_api': True}),
])
def test_override(args, raised_exception, parsed, filled_conf_instance):
    if raised_exception is not None:
        with pytest.raises(raised_exception):
            filled_conf_instance.parse_args(args)
    else:
        output = vars(filled_conf_instance.parse_args(args))
        # we will not be checking func, it is a helper variable
        output.pop("func")
        assert output == parsed
