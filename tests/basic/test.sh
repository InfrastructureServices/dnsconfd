#!/bin/bash
# vim: dict+=/usr/share/beakerlib/dictionary.vim cpt=.,w,b,u,t,i,k
. /usr/share/beakerlib/beakerlib.sh || exit 1
DBUS_NAME=org.freedesktop.resolve1
export RUNID=`uuidgen`

rlJournalStart
    rlPhaseStartSetup
        rlRun "tmp=\$(mktemp -d)" 0 "Create tmp directory"
        rlRun "cp expected_status.json $tmp"
        # dns=none is neccessary, because otherwise resolv.conf is created and
        # mounted by podman as read-only
        #rlRun "podman-compose --podman-run-args='--dns=none' up -d --force-recreate" 0 "Start the compose"
        rlRun "pushd $tmp"
        rlRun "set -o pipefail"
        rlRun "podman network create dnsconfd_network -d=bridge --gateway=192.168.6.1 --subnet=192.168.6.0/24"
        rlRun "dnsconfd_cid=\$(podman run -d --dns='none' --network dnsconfd_network:ip=192.168.6.2 dnsconfd_testing:latest)" 0 "Starting dnsconfd container"
        rlRun "dnsmasq_cid=\$(podman run -d --dns='none' --network dnsconfd_network:ip=192.168.6.3 dnsconfd_dnsmasq:latest --listen-address=192.168.6.3 --address=/address.test.com/192.168.6.3)" 0 "Starting dnsmasq container"
    rlPhaseEnd  

    rlPhaseStartTest
        sleep 3
        rlRun "podman exec $dnsconfd_cid nmcli connection mod eth0 ipv4.dns 192.168.6.3" 0 "Adding dns server to NM active profile"
        sleep 5
        rlRun "podman exec $dnsconfd_cid dnsconfd --dbus-name=$DBUS_NAME -s > status1" 0 "Getting status of dnsconfd"
        rlRun "diff status1 expected_status.json" 0 "Check status"
        rlRun "podman exec $dnsconfd_cid getent hosts address.test.com | grep 192.168.6.3" 0 "Verifying correct address resolution"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "podman stop $dnsconfd_cid" 0 "Stopping dnsconfd container"
        rlRun "podman stop $dnsmasq_cid" 0 "Stopping dnsmasq container"
        sleep 5
        rlRun "podman container rm $dnsconfd_cid" 0 "Removing dnsconfd container"
        rlRun "podman container rm $dnsmasq_cid" 0 "Removing dnsconfd container"
        rlRun "podman network rm dnsconfd_network"
        rlRun "rm -r $tmp" 0 "Remove tmp directory"
    rlPhaseEnd
rlJournalEnd
