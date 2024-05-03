#!/bin/bash

set -e

tempdir=$(mktemp -d)
mkdir "$tempdir"/dnsconfd-0.0.5
cp -r ./* "$tempdir"/dnsconfd-0.0.5
pushd "$tempdir"
tar -czvf "$tempdir"/dnsconfd-0.0.5.tar.gz dnsconfd-0.0.5
popd
mv "$tempdir"/dnsconfd-0.0.5.tar.gz ./distribution
pushd distribution
fedpkg --release=f39 mockbuild
mv ./results_dnsconfd/0.0.5/1.fc39/*.noarch.rpm ../tests
popd
rm -rf "$tempdir"
