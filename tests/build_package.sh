#!/bin/bash

set -e

tempdir=$(mktemp -d)
tar -czvf $tempdir/dnsconfd-2.0.0.tar.gz --transform 's,^\./,dnsconfd-2.0.0/,' .
mkdir SOURCES
cp ./distribution/dnsconfd.sysusers $tempdir/dnsconfd-2.0.0.tar.gz ./SOURCES
# there is a hidden side effect of bb and that is that it copies sources from
# SOURCES directory into binary rpms, however if they are missing, they
# are not copied and scriptlets are left without them
rpmbuild --define "_topdir $PWD" --define "with_asan 1" -bb distribution/dnsconfd.spec
find ./RPMS -name "*.rpm" -exec cp "{}" ./tests \;
rm -rf BUILDROOT RPMS SRPMS SOURCES
rm -rf $tempdir
