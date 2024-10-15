#!/bin/bash
# vim: dict+=/usr/share/beakerlib/dictionary.vim cpt=.,w,b,u,t,i,k
. /usr/share/beakerlib/beakerlib.sh || exit 1
ORIG_DIR=$(pwd)

rlJournalStart
    rlPhaseStartSetup
        rlRun "tmp=\$(mktemp -d)" 0 "Create tmp directory"
        rlRun "pushd $tmp"
        rlRun "set -o pipefail"
        rlRun "podman network create dnsconfd_network --internal -d=bridge --gateway=192.168.6.1 --subnet=192.168.6.0/24"
        # dns=none is neccessary, because otherwise resolv.conf is created and
        # mounted by podman as read-only
        rlRun "dnsconfd_cid=\$(podman run -d --dns='none' --network dnsconfd_network:ip=192.168.6.2 dnsconfd_testing:latest)" 0 "Starting dnsconfd container"
        rlRun "dnsmasq_cid1=\$(podman run -d --dns='none' --network dnsconfd_network:ip=192.168.6.3 localhost/dnsconfd_utilities:latest dnsmasq_entry.sh --listen-address=192.168.6.3 --host-record=address-one.example.com,8.8.8.8)" 0 "Starting dnsmasq container"
        rlRun "dnsmasq_cid2=\$(podman run -d --dns='none' --network dnsconfd_network:ip=192.168.6.4 localhost/dnsconfd_utilities:latest dnsmasq_entry.sh --listen-address=192.168.6.4 --host-record=address-two.example.com,8.8.8.8)" 0 "Starting dnsmasq container"
        rlRun "dnsmasq_cid3=\$(podman run -d --dns='none' --network dnsconfd_network:ip=192.168.6.5 localhost/dnsconfd_utilities:latest dnsmasq_entry.sh --listen-address=192.168.6.5 --host-record=address-three.example.com,8.8.8.8 --host-record=address-four.example.com,8.8.4.4)" 0 "Starting dnsmasq container"
    rlPhaseEnd

    rlPhaseStartTest
        sleep 2
        rlRun "podman exec $dnsconfd_cid /bin/bash -c 'echo api_choice: dnsconfd >> /etc/dnsconfd.conf'" 0 "switching API"
        rlRun "podman exec $dnsconfd_cid systemctl restart dnsconfd" 0 "restarting dnsconfd"
        sleep 2
        rlRun "podman exec $dnsconfd_cid dnsconfd update '[{\"address\":\"192.168.6.3\", \"networks\": [\"8.0.0.0/8\"]}, {\"address\":\"192.168.6.4\", \"networks\": [\"192.168.7.0/24\"]}, {\"address\":\"192.168.6.5\", \"networks\": [\"192.168.8.0/24\", \"8.8.4.0/24\"]}]' 0" 0 "submit update"
        sleep 2
        rlRun "podman exec $dnsconfd_cid dnsconfd status --json > status1" 0 "Getting status of dnsconfd"
        rlAssertNotDiffer status1 $ORIG_DIR/expected_status.json
        rlRun "podman exec $dnsconfd_cid host 8.8.8.8 | grep address-one.example.com" 0 "Verifying correct address resolution"
        rlRun "podman exec $dnsconfd_cid host 8.8.4.4 | grep address-four.example.com" 0 "Verifying correct address resolution"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "podman exec $dnsconfd_cid journalctl -u dnsconfd" 0 "Saving dnsconfd logs"
        rlRun "podman exec $dnsconfd_cid journalctl -u unbound" 0 "Saving unbound logs"
        rlRun "podman exec $dnsconfd_cid ip route" 0 "Saving present routes"
        rlRun "popd"
        rlRun "podman stop -t 0 $dnsconfd_cid $dnsmasq_cid1 $dnsmasq_cid2 $dnsmasq_cid3" 0 "Stopping containers"
        rlRun "podman container rm $dnsconfd_cid $dnsmasq_cid1 $dnsmasq_cid2 $dnsmasq_cid3" 0 "Removing containers"
        rlRun "podman network rm dnsconfd_network" 0 "Removing networks"
        rlRun "rm -r $tmp" 0 "Remove tmp directory"
    rlPhaseEnd
rlJournalEnd
