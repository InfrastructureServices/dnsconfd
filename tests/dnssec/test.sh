#!/bin/bash
# vim: dict+=/usr/share/beakerlib/dictionary.vim cpt=.,w,b,u,t,i,k
. /usr/share/beakerlib/beakerlib.sh || exit 1
DBUS_NAME=org.freedesktop.resolve1
ORIG_DIR=$(pwd)

rlJournalStart
    rlPhaseStartSetup
        rlRun "tmp=\$(mktemp -d)" 0 "Create tmp directory"
        rlRun "cp root.key $tmp/root.key" 0 "Copying root key"
        rlRun "pushd $tmp"
        rlRun "set -o pipefail"
        rlRun "podman network create --internal dnsconfd_network -d=bridge --gateway=192.168.6.1 --subnet=192.168.6.0/24"
        # dns=none is neccessary, because otherwise resolv.conf is created and
        # mounted by podman as read-only
        rlRun "dnsconfd_cid=\$(podman run -d --dns='none' --network dnsconfd_network:ip=192.168.6.2 dnsconfd_testing:latest)" 0 "Starting dnsconfd container"
        rlRun "bind_parent_cid=\$(podman run -d --dns='none' --network dnsconfd_network:ip=192.168.6.3 localhost/dnsconfd_utilities:latest bind_entry.sh)" 0 "Starting bind container"
    rlPhaseEnd

    rlPhaseStartTest
        rlRun "podman exec $dnsconfd_cid /bin/bash -c 'echo \"dnssec_enabled: yes\" >> /etc/dnsconfd.conf'" 0 "Enabling dnssec"
        rlRun "podman cp root.key $dnsconfd_cid:/var/lib/unbound/root.key" 0 "installing root key"
        rlRun "podman exec $dnsconfd_cid sed -i 's/# auto-trust-anchor-file:/auto-trust-anchor-file:/' /etc/unbound/unbound.conf" 0 "setting auto trust anchor file"
        rlRun "podman exec $dnsconfd_cid systemctl restart dnsconfd" 0 "restarting dnsconfd"
        sleep 15
        rlRun "podman exec $dnsconfd_cid nmcli connection mod eth0 ipv4.dns 192.168.6.3" 0 "Adding dns server to NM active profile"
        sleep 5
        rlRun "podman exec $dnsconfd_cid dnsconfd --dbus-name=$DBUS_NAME status --json > status1" 0 "Getting status of dnsconfd"
        rlAssertNotDiffer status1 $ORIG_DIR/expected_status.json
        rlRun "podman exec $dnsconfd_cid getent hosts server.example.com | grep 192.168.6.5" 0 "Verifying correct address resolution"
        rlRun "podman exec $dnsconfd_cid getent hosts not-working.example.com | grep 192.168.6.6" 1 "Verifying correct address resolution"
        rlRun "podman exec $dnsconfd_cid dig not-working.example.com | grep SERVFAIL" 0 "Verifying bad validation"
        rlRun "podman exec $dnsconfd_cid journalctl -u unbound" 0 "getting unbound logs"
        rlRun "podman ps" 0 "Getting running containers"
        rlRun "podman logs $bind_parent_cid" 0 "getting bind container logs"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "podman exec $dnsconfd_cid journalctl -u dnsconfd" 0 "Saving logs"
        rlRun "popd"
        rlRun "podman stop -t 2 $dnsconfd_cid $bind_parent_cid" 0 "Stopping containers"
        rlRun "podman container rm $dnsconfd_cid $bind_parent_cid" 0 "Removing containers"
        rlRun "podman network rm dnsconfd_network" 0 "Removing networks"
        rlRun "rm -r $tmp" 0 "Remove tmp directory"
    rlPhaseEnd
rlJournalEnd
