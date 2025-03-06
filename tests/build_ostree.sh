#!/bin/bash

set -e
# NOTE: we have to install openvpn here, because on CentosStream it is in EPEL and container
# build does not have epel repository
if grep el10 /etc/os-release || grep el9 /etc/os-release; then
  dnf -y --setopt=install_weak_deps=False --releasever=/ --installroot="$PWD/tests/baseroot" install dnf system-release openvpn NetworkManager-openvpn selinux-policy selinux-policy-base
else
  dnf -y --setopt=install_weak_deps=False --use-host-config --installroot="$PWD/tests/baseroot" install dnf system-release openvpn NetworkManager-openvpn selinux-policy selinux-policy-base
fi;
