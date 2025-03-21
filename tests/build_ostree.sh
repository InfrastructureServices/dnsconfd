#!/bin/bash

set -e
if grep el10 /etc/os-release || grep el9 /etc/os-release; then
  dnf -y --setopt=install_weak_deps=False --releasever=/ --installroot="$PWD/tests/baseroot" install dnf system-release openvpn NetworkManager-openvpn selinux-policy selinux-policy-base
  cp -r /etc/yum.repos.d "$PWD/tests/baseroot/etc"
else
  dnf -y --setopt=install_weak_deps=False --use-host-config --installroot="$PWD/tests/baseroot" install dnf system-release openvpn NetworkManager-openvpn selinux-policy selinux-policy-base
fi;
