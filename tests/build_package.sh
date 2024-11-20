#!/bin/bash

set -e

mkdir SOURCES
cp ./distribution/dnsconfd.sysusers ./SOURCES
rm -rf "$tempdir"
# there is a hidden side effect of bb and that is that it copies sources from
# SOURCES directory into binary rpms, however if they are missing, they
# are not copied and scriptlets are left without them
rpmbuild --define "_topdir $PWD" --build-in-place -bb distribution/dnsconfd.spec
find ./RPMS -name "*.rpm" -exec cp "{}" ./tests \;
rm -rf BUILDROOT RPMS SRPMS SOURCES
