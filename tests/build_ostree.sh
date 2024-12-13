#!/bin/bash

if grep f40 /etc/os-release || grep el10 /etc/os-release; then
  dnf -y --setopt=install_weak_deps=False --releasever=/ --installroot="$PWD/tests/baseroot" install dnf "$(rpm -q --whatprovides system-release)" openvpn NetworkManager-openvpn selinux-policy selinux-policy-base
else
  dnf -y --setopt=install_weak_deps=False --use-host-config --installroot="$PWD/tests/baseroot" install dnf "$(rpm -q --whatprovides system-release)" openvpn NetworkManager-openvpn selinux-policy selinux-policy-base
fi;
