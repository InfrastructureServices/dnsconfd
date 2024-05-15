#!/bin/bash
# vim: dict+=/usr/share/beakerlib/dictionary.vim cpt=.,w,b,u,t,i,k
. /usr/share/beakerlib/beakerlib.sh || exit 1
DBUS_NAME=org.freedesktop.resolve1
ORIG_DIR=$(pwd)

rlJournalStart
    rlPhaseStartSetup
        rlRun "set -o pipefail"
        rlRun "podman network create dnsconfd_network --internal -d=bridge --gateway=192.168.6.1 --subnet=192.168.6.0/24"
        # dns=none is neccessary, because otherwise resolv.conf is created and
        # mounted by podman as read-only
        rlRun "dnsconfd_cid=\$(podman run -d --dns='none' --network dnsconfd_network:ip=192.168.6.2 dnsconfd_testing:latest)" 0 "Starting dnsconfd container"
    rlPhaseEnd

    rlPhaseStartTest
        sleep 2
        rlRun "podman exec $dnsconfd_cid /bin/bash -c 'echo nonsense >> /etc/dnsconfd.conf' "
        rlRun "podman exec $dnsconfd_cid systemctl restart dnsconfd" 0 "start dnsconfd"
        sleep 6
        rlRun "podman exec $dnsconfd_cid journalctl -u dnsconfd | grep 'Bad config provided'" 0 "Checking dnsconfd logs"
        rlRun "podman exec $dnsconfd_cid systemctl status dnsconfd" 0 "Verify that dnsconfd is running"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "podman exec $dnsconfd_cid journalctl -u dnsconfd" 0 "Saving logs"
        rlRun "podman stop -t 2 $dnsconfd_cid" 0 "Stopping containers"
        rlRun "podman container rm $dnsconfd_cid" 0 "Removing containers"
        rlRun "podman network rm dnsconfd_network" 0 "Removing networks"
    rlPhaseEnd
rlJournalEnd
