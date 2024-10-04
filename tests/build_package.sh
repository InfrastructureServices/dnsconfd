#!/bin/bash

set -e

tempdir=$(mktemp -d)
mkdir "$tempdir"/dnsconfd-1.4.1
cp -r ./* "$tempdir"/dnsconfd-1.4.1
pushd "$tempdir"
tar -czvf "$tempdir"/dnsconfd-1.4.1.tar.gz dnsconfd-1.4.1
popd
mv "$tempdir"/dnsconfd-1.4.1.tar.gz ./distribution
pushd distribution
fedpkg --release=f40 mockbuild
mv ./results_dnsconfd/1.4.1/1.fc40/*.noarch.rpm ../tests
popd
rm -rf "$tempdir"
