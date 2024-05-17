#!/bin/bash

set -e

tempdir=$(mktemp -d)
mkdir "$tempdir"/dnsconfd-0.0.6
cp -r ./* "$tempdir"/dnsconfd-0.0.6
pushd "$tempdir"
tar -czvf "$tempdir"/dnsconfd-0.0.6.tar.gz dnsconfd-0.0.6
popd
mv "$tempdir"/dnsconfd-0.0.6.tar.gz ./distribution
pushd distribution
fedpkg --release=f39 mockbuild
mv ./results_dnsconfd/0.0.6/1.fc39/*.noarch.rpm ../tests
popd
rm -rf "$tempdir"
