#!/bin/bash

if grep f40 /etc/os-release || grep el10 /etc/os-release || grep el9 /etc/os-release; then
  dnf -y --setopt=install_weak_deps=False --releasever=/ --installroot="$PWD/tests/baseroot" install dnf "$(rpm -q --whatprovides system-release)" openvpn NetworkManager-openvpn selinux-policy selinux-policy-base
else
  dnf -y --setopt=install_weak_deps=False --use-host-config --installroot="$PWD/tests/baseroot" install dnf "$(rpm -q --whatprovides system-release)" openvpn NetworkManager-openvpn selinux-policy selinux-policy-base
fi;
if grep el10 /etc/os-release; then
  dnf -y --setopt=install_weak_deps=False --releasever=/ --installroot="$PWD/tests/baseroot" copr enable tkorbar/unbound-latest-centos centos-stream-10
  dnf -y --setopt=install_weak_deps=False --releasever=/ --installroot="$PWD/tests/baseroot" install -y unbound-1.20.0-9*
  dnf -y --setopt=install_weak_deps=False --releasever=/ --installroot="$PWD/tests/baseroot" copr enable bengal/NetworkManager-dns centos-stream-10
  dnf -y --setopt=install_weak_deps=False --releasever=/ --installroot="$PWD/tests/baseroot" install -y NetworkManager-1.53.0*
elif grep el9 /etc/os-release; then
  dnf -y --setopt=install_weak_deps=False --releasever=/ --installroot="$PWD/tests/baseroot" copr enable tkorbar/unbound-latest-centos centos-stream-9
  dnf -y --setopt=install_weak_deps=False --releasever=/ --installroot="$PWD/tests/baseroot" install -y unbound-1.16.2-17*
  dnf -y --setopt=install_weak_deps=False --releasever=/ --installroot="$PWD/tests/baseroot" copr enable bengal/NetworkManager-dns centos-stream-9
  dnf -y --setopt=install_weak_deps=False --releasever=/ --installroot="$PWD/tests/baseroot" install -y NetworkManager-1.53.0*
elif grep f40 /etc/os-release; then
  dnf -y --setopt=install_weak_deps=False --releasever=/ --installroot="$PWD/tests/baseroot" copr enable bengal/NetworkManager-dns
  dnf -y --setopt=install_weak_deps=False --releasever=/ --installroot="$PWD/tests/baseroot" install -y NetworkManager-1.53.0*
else
  dnf -y --setopt=install_weak_deps=False --use-host-config --installroot="$PWD/tests/baseroot" copr enable bengal/NetworkManager-dns
  dnf -y --setopt=install_weak_deps=False --use-host-config --installroot="$PWD/tests/baseroot" install -y NetworkManager-1.53.0*
fi
