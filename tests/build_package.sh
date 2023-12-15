#!/bin/bash

set -e

python3 setup.py sdist -d ./distribution
pushd distribution
fedpkg local
mv ./noarch/*.noarch.rpm ../tests
popd
