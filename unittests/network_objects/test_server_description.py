import ipaddress

from dnsconfd.network_objects import ServerDescription

import pytest


@pytest.mark.parametrize("value", [
    ("10.0.0.0/24", ['0.0.10.in-addr.arpa']),
    ("10.0.0.0/12",
     ['0.10.in-addr.arpa', '1.10.in-addr.arpa', '2.10.in-addr.arpa', '3.10.in-addr.arpa',
      '4.10.in-addr.arpa', '5.10.in-addr.arpa', '6.10.in-addr.arpa', '7.10.in-addr.arpa',
      '8.10.in-addr.arpa', '9.10.in-addr.arpa', '10.10.in-addr.arpa', '11.10.in-addr.arpa',
      '12.10.in-addr.arpa', '13.10.in-addr.arpa', '14.10.in-addr.arpa', '15.10.in-addr.arpa']),
    ("10.0.0.0/15", ['0.10.in-addr.arpa', '1.10.in-addr.arpa']),
    ("10.0.0.0/22",
     ['0.0.10.in-addr.arpa', '1.0.10.in-addr.arpa', '2.0.10.in-addr.arpa', '3.0.10.in-addr.arpa']),
    ("10.0.0.0/29", ['0.0.0.10.in-addr.arpa', '1.0.0.10.in-addr.arpa', '2.0.0.10.in-addr.arpa',
                     '3.0.0.10.in-addr.arpa', '4.0.0.10.in-addr.arpa', '5.0.0.10.in-addr.arpa',
                     '6.0.0.10.in-addr.arpa', '7.0.0.10.in-addr.arpa']),
    ("10.0.0.1/32", ['1.0.0.10.in-addr.arpa']),
    ("127.0.0.1/32", ['1.0.0.127.in-addr.arpa']),
    ("172.16.0.0/12",
     ['16.172.in-addr.arpa', '17.172.in-addr.arpa', '18.172.in-addr.arpa', '19.172.in-addr.arpa',
      '20.172.in-addr.arpa', '21.172.in-addr.arpa', '22.172.in-addr.arpa', '23.172.in-addr.arpa',
      '24.172.in-addr.arpa', '25.172.in-addr.arpa', '26.172.in-addr.arpa', '27.172.in-addr.arpa',
      '28.172.in-addr.arpa', '29.172.in-addr.arpa', '30.172.in-addr.arpa', '31.172.in-addr.arpa']),
    ("0.0.0.0/0", ['in-addr.arpa']),
    ("2001:DB8::/32", ['8.b.d.0.1.0.0.2.ip6.arpa']),
    ("2001:DB8::/33", ['0.8.b.d.0.1.0.0.2.ip6.arpa', '1.8.b.d.0.1.0.0.2.ip6.arpa', '2.8.b.d.0.1.0.0.2.ip6.arpa',
                       '3.8.b.d.0.1.0.0.2.ip6.arpa', '4.8.b.d.0.1.0.0.2.ip6.arpa', '5.8.b.d.0.1.0.0.2.ip6.arpa',
                       '6.8.b.d.0.1.0.0.2.ip6.arpa', '7.8.b.d.0.1.0.0.2.ip6.arpa']),
    ("2001:DB8::/35", ['0.8.b.d.0.1.0.0.2.ip6.arpa', '1.8.b.d.0.1.0.0.2.ip6.arpa']),
    ("2001:DB8::/48", ['0.0.0.0.8.b.d.0.1.0.0.2.ip6.arpa']),
    ("2001:DB8::/64", ['0.0.0.0.0.0.0.0.8.b.d.0.1.0.0.2.ip6.arpa']),
    ("2001:DB8::/60", ['0.0.0.0.0.0.0.8.b.d.0.1.0.0.2.ip6.arpa']),
    ("2001:DB8::/51", ['0.0.0.0.0.8.b.d.0.1.0.0.2.ip6.arpa', '1.0.0.0.0.8.b.d.0.1.0.0.2.ip6.arpa']),
    ("2001:DB8::/62", ['0.0.0.0.0.0.0.0.8.b.d.0.1.0.0.2.ip6.arpa', '1.0.0.0.0.0.0.0.8.b.d.0.1.0.0.2.ip6.arpa',
                       '2.0.0.0.0.0.0.0.8.b.d.0.1.0.0.2.ip6.arpa', '3.0.0.0.0.0.0.0.8.b.d.0.1.0.0.2.ip6.arpa']),
    ("2001:DB8:1234:a000::/52", ['a.4.3.2.1.8.b.d.0.1.0.0.2.ip6.arpa']),
    ("::1/128", ['1.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.ip6.arpa']),
    ("::/0", ['ip6.arpa']),
]
                         )
def test_get_rev_zones(value):
    nets = ipaddress.ip_network(value[0])
    assert ServerDescription(4, b"\x00\x00\x00\x00", networks=[nets]).get_rev_zones() == value[1]