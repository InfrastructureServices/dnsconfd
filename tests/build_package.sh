#!/bin/bash

set -e

python3 setup.py sdist -d ./distribution
cp LICENSE ./distribution/
pushd distribution
fedpkg --release=f39 mockbuild
mv ./results_dnsconfd/0.0.1/1.fc39/*.noarch.rpm ../tests
popd
