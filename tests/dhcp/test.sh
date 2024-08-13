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
        # dns=none is neccessary, because otherwise resolv.conf is created and
        # mounted by podman as read-only
        rlRun "dhcp_cid=\$(podman run -d --cap-add=NET_RAW --network dnsconfd_network:ip=192.168.6.5 localhost/dnsconfd_utilities:latest dhcp_entry.sh /etc/dhcp/dhcpd-empty.conf)" 0 "Starting dhcpd container with empty dns"
        rlRun "dnsconfd_cid=\$(podman run -d --cap-add=NET_ADMIN --cap-add=NET_RAW --dns='none' --network dnsconfd_network:ip=192.168.6.2 dnsconfd_testing:latest)" 0 "Starting dnsconfd container"
        rlRun "dnsmasq1_cid=\$(podman run -d --dns='none' --network dnsconfd_network:ip=192.168.6.3 localhost/dnsconfd_utilities:latest dnsmasq_entry.sh --listen-address=192.168.6.3 --address=/first-address.test.com/192.168.6.3)" 0 "Starting first dnsmasq container"
        rlRun "dnsmasq2_cid=\$(podman run -d --dns='none' --network dnsconfd_network:ip=192.168.6.4 localhost/dnsconfd_utilities:latest dnsmasq_entry.sh --listen-address=192.168.6.4 --address=/second-address.test.com/192.168.6.4)" 0 "Starting second dnsmasq container"
    rlPhaseEnd

    rlPhaseStartTest
        sleep 2
        # This elaborative change of eth0 connection causes that NetworkManager will receive
        # the exact same address from dhcp that podman assigned to the container. Without this,
        # routing tables that podman creates would not be correct and we would face error during
        # clean up after the container
        rlRun "podman exec $dnsconfd_cid nmcli connection mod eth0 ipv4.gateway '' ipv4.addr '' ipv4.method auto" 0 "Setting eth0 to autoconfiguration"
        sleep 3
        rlRun "podman stop -t 2 $dhcp_cid" 0 "Stopping containers"
        rlRun "podman container rm $dhcp_cid" 0 "Removing containers"
        rlRun "dhcp_cid=\$(podman run -d --cap-add=NET_RAW --network dnsconfd_network:ip=192.168.6.5 localhost/dnsconfd_utilities:latest dhcp_entry.sh /etc/dhcp/dhcpd-common.conf)" 0 "Starting dhcpd container with dns list"
        sleep 3
        # restart of NetworkManager ensures new dhcp request
        rlRun "podman exec $dnsconfd_cid systemctl restart NetworkManager"
        sleep 5
        rlRun "podman exec $dnsconfd_cid dnsconfd --dbus-name=$DBUS_NAME status --json > status1" 0 "Getting status of dnsconfd"
        # in this test we are verifying that the DNS of non-wireless interface has higher priority
        # than the wireless one
        rlAssertNotDiffer status1 $ORIG_DIR/expected_status.json
        rlRun "podman exec $dnsconfd_cid getent hosts first-address.test.com | grep 192.168.6.3" 0 "Verifying correct address resolution"
        rlRun "podman exec $dnsconfd_cid getent hosts second-address.test.com | grep 192.168.6.4" 0 "Verifying correct address resolution"
        rlRun "podman exec $dnsconfd_cid getent hosts second-address | grep 192.168.6.4" 0 "Verifying correct address resolution"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "podman exec $dnsconfd_cid journalctl -u dnsconfd" 0 "Saving dnsconfd logs"
        rlRun "podman exec $dnsconfd_cid journalctl -u unbound" 0 "Saving unbound logs"
        rlRun "podman exec $dnsconfd_cid ip route" 0 "Saving present routes"
        rlRun "popd"
        rlRun "podman stop -t 2 $dnsconfd_cid $dnsmasq1_cid $dnsmasq2_cid $dhcp_cid" 0 "Stopping containers"
        rlRun "podman container rm $dnsconfd_cid $dnsmasq1_cid $dnsmasq2_cid $dhcp_cid" 0 "Removing containers"
        rlRun "podman network rm dnsconfd_network" 0 "Removing networks"
        rlRun "rm -r $tmp" 0 "Remove tmp directory"
    rlPhaseEnd
rlJournalEnd
