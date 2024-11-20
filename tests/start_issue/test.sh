#!/bin/bash
# vim: dict+=/usr/share/beakerlib/dictionary.vim cpt=.,w,b,u,t,i,k
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "set -o pipefail"
        rlRun "podman network create dnsconfd_network --internal -d=bridge --gateway=192.168.6.1 --subnet=192.168.6.0/24"
        # dns=none is neccessary, because otherwise resolv.conf is created and
        # mounted by podman as read-only
        rlRun "dnsconfd_cid=\$(podman run -d --dns='none' --network dnsconfd_network:ip=192.168.6.2 dnsconfd_testing:latest)" 0 "Starting dnsconfd container"
    rlPhaseEnd

    rlPhaseStartTest
        rlRun "podman exec $dnsconfd_cid systemctl start network-online.target"
        rlRun "podman exec $dnsconfd_cid systemctl stop dnsconfd" 0 "stop dnsconfd"
        rlRun "podman exec $dnsconfd_cid sed -i 's/ExecStart=.*/ExecStart=false/g' /usr/lib/systemd/system/unbound.service" 0 "breaking unbound"
        rlRun "podman exec $dnsconfd_cid systemctl daemon-reload" 0 "reload systemd units"
        rlRun "podman exec $dnsconfd_cid systemctl start dnsconfd" 1 "start dnsconfd"
        rlRun "podman exec $dnsconfd_cid journalctl -u dnsconfd | grep -e 'TIMEOUT' -e 'START_FAIL'" 0 "Checking dnsconfd logs"
        rlRun "podman exec $dnsconfd_cid systemctl status dnsconfd" 3 "Verify that dnsconfd is stopped"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "podman exec $dnsconfd_cid journalctl -u dnsconfd" 0 "Saving dnsconfd logs"
        rlRun "podman exec $dnsconfd_cid journalctl -u unbound" 0 "Saving unbound logs"
        rlRun "podman exec $dnsconfd_cid ip route" 0 "Saving present routes"
        rlRun "podman stop -t 0 $dnsconfd_cid" 0 "Stopping containers"
        rlRun "podman container rm $dnsconfd_cid" 0 "Removing containers"
        rlRun "podman network rm dnsconfd_network" 0 "Removing networks"
    rlPhaseEnd
rlJournalEnd
