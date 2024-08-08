#!/bin/bash
# vim: dict+=/usr/share/beakerlib/dictionary.vim cpt=.,w,b,u,t,i,k
. /usr/share/beakerlib/beakerlib.sh || exit 1
DBUS_NAME=org.freedesktop.resolve1
ORIG_DIR=$(pwd)

rlJournalStart
    rlPhaseStartSetup
        rlRun "tmp=\$(mktemp -d)" 0 "Create tmp directory"
        rlRun "cp ./ca_cert.pem $tmp/ca_cert.pem" 0 "Copying CA certificate"
        rlRun "cp ./dnsconfd.conf $tmp/dnsconfd.conf" 0 "Copying config file"
        rlRun "pushd $tmp"
        rlRun "set -o pipefail"
        rlRun "podman network create dnsconfd_network --internal -d=bridge --gateway=192.168.6.1 --subnet=192.168.6.0/24"
        # dns=none is neccessary, because otherwise resolv.conf is created and
        # mounted by podman as read-only
        rlRun "dnsconfd_cid=\$(podman run -d --dns='none' --network dnsconfd_network:ip=192.168.6.2 dnsconfd_testing:latest)" 0 "Starting dnsconfd container"
        rlRun "bind_cid=\$(podman run -d --dns='none' --network dnsconfd_network:ip=192.168.6.3 localhost/dnsconfd_utilities:latest bind_entry.sh)" 0 "Starting dnsmasq container"
    rlPhaseEnd

    rlPhaseStartTest
        rlRun "podman cp dnsconfd.conf $dnsconfd_cid://etc/dnsconfd.conf"
        rlRun "podman cp ca_cert.pem $dnsconfd_cid://etc/pki/ca-trust/source/anchors/ca_cert.pem" 0 "Installing CA"
        rlRun "podman exec $dnsconfd_cid update-ca-trust extract" 0 "updating CA trust"
        # this is necessary, because if ca trust is not in place before unbound start then verification of
        # server certificate fails
        # and we need new configuration
        rlRun "podman exec $dnsconfd_cid systemctl restart dnsconfd"
        sleep 5
        rlRun "podman exec $dnsconfd_cid dnsconfd --dbus-name=$DBUS_NAME status --json > status1" 0 "Getting status of dnsconfd"
        rlAssertNotDiffer status1 $ORIG_DIR/expected_status.json
        rlRun "podman exec $dnsconfd_cid getent hosts server.example.com | grep 192.168.6.5" 0 "Verifying correct address resolution"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "podman exec $dnsconfd_cid journalctl -u dnsconfd" 0 "Saving logs"
        rlRun "popd"
        rlRun "podman stop -t 2 $dnsconfd_cid $bind_cid" 0 "Stopping containers"
        rlRun "podman container rm $dnsconfd_cid $bind_cid" 0 "Removing containers"
        rlRun "podman network rm dnsconfd_network" 0 "Removing networks"
        rlRun "rm -r $tmp" 0 "Remove tmp directory"
    rlPhaseEnd
rlJournalEnd
