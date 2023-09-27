#!/bin/bash

set -e

python3 setup.py sdist -d ./
fedpkg local
mv ./noarch/*.noarch.rpm ./tests

podman build tests -f tests/dnsconfd.Dockerfile -t dnsconfd_testing

podman build tests -f tests/dnsmasq.Dockerfile -t dnsconfd_dnsmasq
podman build tests -f tests/dhcp.Dockerfile -t dnsconfd_dhcp
podman build tests -f tests/vpn.Dockerfile -t dnsconfd_vpn
