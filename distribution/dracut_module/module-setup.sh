#!/usr/bin/bash

check() {
    require_binaries micro-dnsconfd || return 1
    return 0
}

depends() {
    # because of pid file we need sysusers to create unbound user
    echo dbus systemd unbound systemd-sysusers network-manager
    return 0
}

install() {
    inst_simple /usr/lib/systemd/system/micro-dnsconfd.service
    inst_simple "$moddir/unbound_non_empty.conf" /etc/systemd/system/unbound.service.d/unbound_non_empty.conf
    inst_simple "$moddir/micro_dnsconfd_no_fail.conf" /etc/systemd/system/micro-dnsconfd.service.d/micro_dnsconfd_no_fail.conf
    inst_simple /usr/lib/sysusers.d/dnsconfd.conf
    inst_simple /usr/bin/micro-dnsconfd
    inst_simple /usr/lib/tmpfiles.d/dnsconfd.conf
    inst_simple /etc/unbound/conf.d/unbound.conf
    inst_simple /etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem
    inst_multiple -o /etc/pki/dns/extracted/pem/*

    $SYSTEMCTL -q --root "$initdir" enable micro-dnsconfd.service
}
