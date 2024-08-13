#!/bin/bash
# vim: dict+=/usr/share/beakerlib/dictionary.vim cpt=.,w,b,u,t,i,k
. /usr/share/beakerlib/beakerlib.sh || exit 1
DBUS_NAME=org.freedesktop.resolve1
ORIG_DIR=$(pwd)

rlJournalStart
    rlPhaseStartSetup
        rlRun "tmp=\$(mktemp -d)" 0 "Create tmp directory"
        rlRun "pushd $tmp"
        rlRun "set -o pipefail"
        rlRun "podman network create dnsconfd_network --internal -d=bridge --gateway=192.168.6.1 --subnet=192.168.6.0/24"
        rlRun "podman network create dnsconfd_network2 --internal -d=bridge --gateway=192.168.7.1 --subnet=192.168.7.0/24"
        # dns=none is neccessary, because otherwise resolv.conf is created and
        # mounted by podman as read-only
        rlRun "dnsconfd_cid=\$(podman run -d --dns='none' --network dnsconfd_network:ip=192.168.6.2 --network dnsconfd_network2:ip=192.168.7.2 dnsconfd_testing:latest)" 0 "Starting dnsconfd container"
        rlRun "dnsmasq1_cid=\$(podman run -d --dns='none' --network dnsconfd_network:ip=192.168.6.3 localhost/dnsconfd_utilities:latest dnsmasq_entry.sh --listen-address=192.168.6.3 --address=/first-address.test.com/192.168.6.3)" 0 "Starting first dnsmasq container"
        rlRun "dnsmasq2_cid=\$(podman run -d --dns='none' --network dnsconfd_network2:ip=192.168.7.3 localhost/dnsconfd_utilities:latest dnsmasq_entry.sh --listen-address=192.168.7.3 --address=/first-address.test.com/192.168.7.3 --address=/second-address.test.com/192.168.8.3)" 0 "Starting first dnsmasq container"
    rlPhaseEnd

    rlPhaseStartTest
        sleep 2
        rlRun "podman exec $dnsconfd_cid /bin/bash -c 'nmcli connection show eth0 | grep 192.168.6.2 && mkdir -p /tmp/is_wireless/eth0/wireless && nmcli connection mod eth0 ipv4.dns 192.168.6.3 || true'" 0 "Adding dns server to the first NM active profile"
        rlRun "podman exec $dnsconfd_cid /bin/bash -c 'nmcli connection show eth0 | grep 192.168.7.2 && nmcli connection mod eth0 ipv4.dns 192.168.7.3 || true'" 0 "Adding dns server to the first NM active profile"
        rlRun "podman exec $dnsconfd_cid /bin/bash -c 'nmcli connection show eth1 | grep 192.168.6.2 && mkdir -p /tmp/is_wireless/eth1/wireless && nmcli connection mod eth1 ipv4.dns 192.168.6.3 || true'" 0 "Adding dns server to the second NM active profile"
        rlRun "podman exec $dnsconfd_cid /bin/bash -c 'nmcli connection show eth1 | grep 192.168.7.2 && nmcli connection mod eth1 ipv4.dns 192.168.7.3 || true'" 0 "Adding dns server to the second NM active profile"
        sleep 2
        # in this test we are verifying that the DNS of non-wireless interface has higher priority
        # than the wireless one
        # rlRun "diff status1 $ORIG_DIR/expected_status.json || diff status1 $ORIG_DIR/expected_status2.json" 0 "verifying status"
        rlRun "podman exec $dnsconfd_cid getent hosts first-address.test.com | grep 192.168.7.3" 0 "Verifying correct address resolution"
        rlRun "podman exec $dnsconfd_cid getent hosts second-address.test.com | grep 192.168.8.3" 0 "Verifying correct address resolution"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "podman exec $dnsconfd_cid journalctl -u dnsconfd" 0 "Saving dnsconfd logs"
        rlRun "podman exec $dnsconfd_cid journalctl -u unbound" 0 "Saving unbound logs"
        rlRun "podman exec $dnsconfd_cid ip route" 0 "Saving present routes"
        rlRun "popd"
        rlRun "podman stop -t 2 $dnsconfd_cid $dnsmasq1_cid $dnsmasq2_cid" 0 "Stopping containers"
        rlRun "podman container rm $dnsconfd_cid $dnsmasq1_cid $dnsmasq2_cid" 0 "Removing containers"
        rlRun "podman network rm dnsconfd_network dnsconfd_network2" 0 "Removing networks"
        rlRun "rm -r $tmp" 0 "Remove tmp directory"
    rlPhaseEnd
rlJournalEnd
