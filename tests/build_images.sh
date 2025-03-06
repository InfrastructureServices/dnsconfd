#!/bin/bash

set -e

podman build tests -f tests/dnsconfd.Dockerfile -t dnsconfd_testing
podman build tests -f tests/dnsconfd-test-utilities.Dockerfile -t localhost/dnsconfd_utilities:latest
