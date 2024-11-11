#!/bin/bash
# vim: dict+=/usr/share/beakerlib/dictionary.vim cpt=.,w,b,u,t,i,k
. /usr/share/beakerlib/beakerlib.sh || exit 1
. ../dnsconfd_helper_functions.sh || exit 1
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
        rlRun "dnsmasq_cid=\$(podman run -d --dns='none' --network dnsconfd_network:ip=192.168.6.3 localhost/dnsconfd_utilities:latest dnsmasq_entry.sh --listen-address=192.168.6.3 --address=/address.test.com/192.168.6.3)" 0 "Starting dnsmasq container"
    rlPhaseEnd

    rlPhaseStartTest
        rlRun "podman exec $dnsconfd_cid /bin/bash -c 'echo api_choice: dnsconfd >> /etc/dnsconfd.conf'" 0 "switching API"
        rlRun "podman exec $dnsconfd_cid systemctl restart dnsconfd" 0 "restarting dnsconfd"
        sleep 2
        rlRun "podman exec $dnsconfd_cid dnsconfd update 'dns+udp://192.168.6.3?interface=eth0'" 0 "submit update"
        sleep 2
        rlRun "podman exec $dnsconfd_cid dnsconfd status --json | jq_filter_general > status" 0 "Getting status of dnsconfd"
        rlAssertNotDiffer status $ORIG_DIR/expected_status1.json
        rlRun "podman exec $dnsconfd_cid dnsconfd update 'dns+udp://192.168.6.3?interface=eth0' 'dns+tls://[2001:0DB8::1]:9000?domain=example.com&domain=example.org&validation=yes'" 0 "submit update"
        sleep 2
        rlRun "podman exec $dnsconfd_cid dnsconfd status --json | jq_filter_general > status" 0 "Getting status of dnsconfd"
        rlAssertNotDiffer status $ORIG_DIR/expected_status2.json
        rlRun "podman exec $dnsconfd_cid dnsconfd update 'dns+udp://1.1.1.1.1.1.1.1?interface=eth0'" 1 "submit bad update"
        rlAssertNotDiffer status $ORIG_DIR/expected_status2.json
        rlRun "podman exec $dnsconfd_cid dnsconfd update 'dns+udp://192.168.6.3' 'dns+udp://192.168.7.3' --mode 2 --search example.com example.org" 0 "submit update with search"
        sleep 2
        rlRun "podman exec $dnsconfd_cid dnsconfd status --json | jq_filter_general > status" 0 "Getting status of dnsconfd"
        rlAssertNotDiffer status $ORIG_DIR/expected_status3.json
        rlRun "podman exec $dnsconfd_cid dnsconfd update" 0 "submit update"
        sleep 2
        rlRun "podman exec $dnsconfd_cid dnsconfd status --json | jq_filter_general > status" 0 "Getting status of dnsconfd"
        rlAssertNotDiffer status $ORIG_DIR/expected_status4.json
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
