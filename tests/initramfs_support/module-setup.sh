#!/usr/bin/bash

check() {
    require_binaries /usr/bin/getent || return 1
    return 0
}

depends() {
    return 0
}

install() {
    inst_simple "$moddir/test-resolve.service" /usr/lib/systemd/system/test-resolve.service
    inst_simple /usr/bin/getent

    $SYSTEMCTL -q --root "$initdir" enable test-resolve.service
}
