#!/bin/bash
# vim: dict+=/usr/share/beakerlib/dictionary.vim cpt=.,w,b,u,t,i,k
. /usr/share/beakerlib/beakerlib.sh || exit 1
. ../dnsconfd_helper_functions.sh || exit 1
ORIG_DIR=$(pwd)

rlJournalStart
    rlPhaseStartSetup
        if rlTestVersion "$(rpm -q --queryformat '%{VERSION}' dnsconfd)" "<" "1.7.3"; then
          # this test works only in version >= 1.7.2
          rlLog "TEST SKIPPED"
          rlPhaseEnd
          rlJournalEnd
          exit 0
        fi
        rlRun "tmp=\$(mktemp -d)" 0 "Create tmp directory"
        rlRun "pushd $tmp"
        rlRun "set -o pipefail"
        rlRun "podman network create dnsconfd_network --internal -d=bridge --gateway=192.168.6.1 --subnet=192.168.6.0/24"
        # dns=none is neccessary, because otherwise resolv.conf is created and
        # mounted by podman as read-only
        rlRun "dnsconfd_cid=\$(podman run --privileged -d --dns='none' --network dnsconfd_network:ip=192.168.6.2 dnsconfd_testing:latest)" 0 "Starting dnsconfd container"
        rlRun "dnsmasq_cid1=\$(podman run -d --dns='none' --network dnsconfd_network:ip=192.168.6.3 localhost/dnsconfd_utilities:latest dnsmasq_entry.sh --listen-address=192.168.6.3 --address=/address.example.com/192.168.6.3)" 0 "Starting dnsmasq container"
        rlRun "dnsmasq_cid2=\$(podman run -d --dns='none' --network dnsconfd_network:ip=192.168.6.4 localhost/dnsconfd_utilities:latest dnsmasq_entry.sh --listen-address=192.168.6.4 --address=/address.subdomain.example.com/192.168.6.4)" 0 "Starting dnsmasq container"
        rlRun "dnsmasq_cid3=\$(podman run -d --dns='none' --network dnsconfd_network:ip=192.168.6.5 localhost/dnsconfd_utilities:latest dnsmasq_entry.sh --listen-address=192.168.6.5 --address=/address2.example.com/192.168.6.5)" 0 "Starting dnsmasq container"
    rlPhaseEnd

    rlPhaseStartTest
        rlRun "podman exec $dnsconfd_cid systemctl start network-online.target"
        rlRun "podman exec $dnsconfd_cid dnsconfd update --json '[{\"address\":\"192.168.6.3\", \"priority\":20}, {\"address\":\"192.168.6.4\", \"routing_domains\": [\".\", \"subdomain.example.com\"], \"priority\":10}, {\"address\":\"192.168.6.5\", \"priority\":0}]' --mode 0" 0 "submit update"
        sleep 2
        rlRun "podman exec $dnsconfd_cid dnsconfd status --json | jq_filter_general > status1" 0 "Getting status of dnsconfd"
        rlAssertNotDiffer status1 $ORIG_DIR/expected_status1.json
        rlRun "podman exec $dnsconfd_cid dnsconfd update --json '[{\"address\":\"192.168.6.3\", \"priority\":0}, {\"address\":\"192.168.6.4\", \"routing_domains\": [\".\", \"subdomain.example.com\"], \"priority\":0}, {\"address\":\"192.168.6.5\", \"priority\":0}]' --mode 0" 0 "submit update"
        sleep 2
        rlRun "podman exec $dnsconfd_cid dnsconfd status --json | jq_filter_general > status2" 0 "Getting status of dnsconfd"
        rlAssertNotDiffer status2 $ORIG_DIR/expected_status2.json
        rlRun "podman exec $dnsconfd_cid dnsconfd update --json '[{\"address\":\"192.168.6.3\", \"priority\":10}, {\"address\":\"192.168.6.4\", \"routing_domains\": [\".\", \"subdomain.example.com\"], \"priority\":0}, {\"address\":\"192.168.6.5\", \"priority\":10}]' --mode 0" 0 "submit update"
        sleep 2
        rlRun "podman exec $dnsconfd_cid dnsconfd status --json | jq_filter_general > status3" 0 "Getting status of dnsconfd"
        rlAssertNotDiffer status3 $ORIG_DIR/expected_status3.json
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
