#!/bin/bash
# vim: dict+=/usr/share/beakerlib/dictionary.vim cpt=.,w,b,u,t,i,k
. /usr/share/beakerlib/beakerlib.sh || exit 1
. ../dnsconfd_helper_functions.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "tmp=\$(mktemp -d)" 0 "Create tmp directory"
        rlRun "cp expected_status.json $tmp"
        rlRun "pushd $tmp"
        rlRun "podman network create dnsconfd_network --internal -d=bridge --gateway=192.168.6.1 --subnet=192.168.6.0/24"
        # dns=none is neccessary, because otherwise resolv.conf is created and
        # mounted by podman as read-only
        rlRun "dnsconfd_cid=\$(podman run -d --dns='none' --privileged --network dnsconfd_network:ip=192.168.6.2 dnsconfd_testing:latest)" 0 "Starting dnsconfd container"
        rlRun "dnsmasq_cid=\$(podman run -d --dns='none' --network dnsconfd_network:ip=192.168.6.3 localhost/dnsconfd_utilities:latest dnsmasq_entry.sh --listen-address=192.168.6.3 --address=/address.test.com/192.168.6.3)" 0 "Starting dnsmasq container"
    rlPhaseEnd

    rlPhaseStartTest
        rlRun "podman exec $dnsconfd_cid systemctl start network-online.target" 0 "Waiting for network setup"
        rlRun "podman exec $dnsconfd_cid nmcli connection mod eth0 ipv4.dns 192.168.6.3" \
            0 "Adding dns server to NM active profile"
        rlRun "podman exec $dnsconfd_cid nmcli connection up eth0" 0 "Bringing the connection up"
        # FIXME workaround of NM DAD issue
        rlRun "podman exec $dnsconfd_cid nmcli g reload"
        rlRun "podman exec $dnsconfd_cid dnsconfd status --json | jq_filter_general > status1" \
            0 "Getting status of dnsconfd"
        rlAssertNotDiffer status1 expected_status.json
        rlRun "podman exec $dnsconfd_cid getent hosts address.test.com | grep 192.168.6.3" \
            0 "Verifying correct address resolution"
        rlRun "podman exec $dnsconfd_cid systemctl stop dnsconfd" 0 "Stopping dnsconfd"
        rlRun "podman exec $dnsconfd_cid dnsconfd config nm_disable" \
            0 "disabling dnsconfd in Network Manager"
        sleep 2
        rlRun "podman exec $dnsconfd_cid getent hosts address.test.com | grep 192.168.6.3" \
            0 "Verifying correct address resolution after cleanup"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "podman exec $dnsconfd_cid journalctl -u dnsconfd" 0 "Saving dnsconfd logs"
        rlRun "podman exec $dnsconfd_cid journalctl -u unbound" 0 "Saving unbound logs"
        rlRun "podman exec $dnsconfd_cid ip route" 0 "Saving present routes"
        rlRun "popd"
        rlRun "podman stop -t 0 $dnsconfd_cid $dnsmasq_cid" 0 "Stopping containers"
        rlRun "podman container rm $dnsconfd_cid $dnsmasq_cid" 0 "Removing containers"
        rlRun "podman network rm dnsconfd_network" 0 "Removing networks"
        rlRun "rm -r $tmp" 0 "Remove tmp directory"
    rlPhaseEnd
rlJournalEnd
