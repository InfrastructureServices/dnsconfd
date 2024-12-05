#!/usr/bin/bash

check() {
    require_binaries dnsconfd || return 1
    # the module will be only included if explicitly required
    return 255
}

depends() {
    # because of pid file we need sysusers to create unbound user
    echo dbus systemd unbound systemd-sysusers network-manager
    return 0
}

install() {
    inst_simple /usr/lib/systemd/system/micro-dnsconfd.service
    inst_simple "$moddir/unbound_dnsconfd_dependency.conf" /etc/systemd/system/unbound.service.d/unbound_dnsconfd_dependency.conf
    inst_simple /usr/lib/sysusers.d/dnsconfd.conf
    inst_simple /usr/bin/micro-dnsconfd
    inst_simple /usr/lib/tmpfiles.d/dnsconfd.conf
    inst_simple /usr/lib/tmpfiles.d/dnsconfd-unbound.conf
    inst_simple /etc/unbound/conf.d/unbound.conf
    inst_simple /etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem

    $SYSTEMCTL -q --root "$initdir" enable micro-dnsconfd.service
}
