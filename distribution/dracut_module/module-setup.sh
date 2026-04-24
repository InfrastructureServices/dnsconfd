#!/usr/bin/bash

check() {
    require_binaries dnsconfd || return 1
    return 0
}

depends() {
    # because of pid file we need sysusers to create unbound user
    echo dbus systemd unbound systemd-sysusers network-manager
    return 0
}

install() {
    inst_simple /usr/bin/dnsconfd
    inst_simple /usr/share/dbus-1/system.d/com.redhat.dnsconfd.conf
    inst_simple /usr/share/dbus-1/system-services/com.redhat.dnsconfd.service
    inst_simple /etc/sysconfig/dnsconfd
    inst_simple /etc/dnsconfd/dnsconfd.conf
    inst_simple /usr/lib/systemd/system/dnsconfd.service
    inst_simple /usr/libexec/dnsconfd-prepare
    inst_simple /usr/libexec/dnsconfd-cleanup

    inst_simple /usr/lib/sysusers.d/dnsconfd.conf

    inst_simple /usr/lib/tmpfiles.d/dnsconfd.conf
    inst_simple /usr/lib/systemd/system/unbound.service.d/dnsconfd.conf
    inst_simple /usr/lib/systemd/system/dnsconfd.service.d/dnsconfd-unbound-control.conf
    inst_simple /usr/lib/tmpfiles.d/dnsconfd-unbound.conf
    inst_simple /usr/lib/systemd/system/dnsconfd-unbound-control.path
    inst_simple /usr/lib/systemd/system/dnsconfd-unbound-control.service
    inst_simple /usr/libexec/dnsconfd-unbound-control.sh

    inst_simple /etc/unbound/conf.d/unbound.conf

    inst_simple /etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem
    inst_multiple -o /etc/pki/dns/extracted/pem/*

    $SYSTEMCTL -q --root "$initdir" enable dnsconfd.service
}
