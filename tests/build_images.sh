#!/bin/bash

set -e

python3 setup.py sdist
mv ./dist/*.tar.gz ./
fedpkg --release=f38 mockbuild
mv ./results_dnsconfd/0.0.1/37.fc38/*.noarch.rpm ./tests

pushd tests
podman build . -f dnsconfd.Dockerfile -t dnsconfd_testing
podman build . -f dnsmasq.Dockerfile -t dnsconfd_dnsmasq
popd
