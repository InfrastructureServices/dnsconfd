#!/bin/bash

set -e

python3 setup.py sdist -d ./distribution
cp ./LICENSE distribution/LICENSE
pushd distribution
fedpkg local
mv ./noarch/*.noarch.rpm ../tests
popd
