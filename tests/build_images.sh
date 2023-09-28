#!/bin/bash

set -e

python3 setup.py sdist -d ./
fedpkg local
mv ./noarch/*.noarch.rpm ./tests

podman build tests -f tests/dnsconfd.Dockerfile -t dnsconfd_testing

if [ "$1" = "-q" ]; then
    echo "Using images from quay"
    podman pull quay.io/tkorbar/dnsconfd_utilities:latest
    podman tag quay.io/tkorbar/dnsconfd_utilities:latest localhost/dnsconfd_utilities:latest
else
    echo "Rebuilding testing container image"
    podman build tests -f tests/dnsconfd-test-utilities.Dockerfile -t localhost/dnsconfd_utilities:latest
fi
