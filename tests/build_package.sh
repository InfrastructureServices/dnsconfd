#!/bin/bash

set -e

tempdir=$(mktemp -d)
mkdir "$tempdir"/dnsconfd-1.0.0
cp -r ./* "$tempdir"/dnsconfd-1.0.0
pushd "$tempdir"
tar -czvf "$tempdir"/dnsconfd-1.0.0.tar.gz dnsconfd-1.0.0
popd
mv "$tempdir"/dnsconfd-1.0.0.tar.gz ./distribution
pushd distribution
fedpkg --release=f40 mockbuild
mv ./results_dnsconfd/1.0.0/1.fc40/*.noarch.rpm ../tests
popd
rm -rf "$tempdir"
