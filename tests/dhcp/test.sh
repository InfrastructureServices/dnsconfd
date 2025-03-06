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
        rlRun "podman network create dnsconfd_network --internal -d=bridge --subnet=192.168.6.0/24 --gateway=192.168.6.1 --subnet=2001:db8::/64 --gateway=2001:db8::1"
        # dns=none is neccessary, because otherwise resolv.conf is created and
        # mounted by podman as read-only
        rlRun "dhcp4_cid=\$(podman run -d --cap-add=NET_RAW --network dnsconfd_network:ip=192.168.6.5,ip=2001:db8::a1 localhost/dnsconfd_utilities:latest dhcp_entry.sh /etc/dhcp/dhcpd-empty.conf)" 0 "Starting dhcpd container with empty dns"
        rlRun "dhcp6_cid=\$(podman run -d --cap-add=NET_RAW --privileged --network dnsconfd_network:ip=2001:db8::4,ip=192.168.6.20 localhost/dnsconfd_utilities:latest ratool_entry.sh)" 0 "Starting dhcpd6 container"
        rlRun "dnsconfd_cid=\$(podman run -d --cap-add=NET_ADMIN --cap-add=NET_RAW --privileged --dns='none' --network dnsconfd_network:interface_name=eth0,ip=192.168.6.2,ip=2001:db8::2 dnsconfd_testing:latest)" 0 "Starting dnsconfd container"
        rlRun "dnsmasq1_cid=\$(podman run -d --dns='none' --network dnsconfd_network:ip=192.168.6.3,ip=2001:db8::a2 localhost/dnsconfd_utilities:latest dnsmasq_entry.sh --listen-address=192.168.6.3 --address=/first-address.test.com/192.168.6.3)" 0 "Starting first dnsmasq container"
        rlRun "dnsmasq2_cid=\$(podman run -d --dns='none' --network dnsconfd_network:ip=192.168.6.4,ip=2001:db8::a3 localhost/dnsconfd_utilities:latest dnsmasq_entry.sh --listen-address=192.168.6.4 --address=/second-address.test.com/192.168.6.4)" 0 "Starting second dnsmasq container"
        rlRun "dnsmasq3_cid=\$(podman run -d --dns='none' --network dnsconfd_network:ip=2001:db8::3 localhost/dnsconfd_utilities:latest dnsmasq_entry.sh --listen-address=2001:db8::3 --address=/third-address.test.com/2001:db8::3)" 0 "Starting second dnsmasq container"
    rlPhaseEnd

    rlPhaseStartTest
        rlRun "podman exec $dnsconfd_cid systemctl start network-online.target"
        rlRun "podman exec $dnsconfd_cid nmcli connection mod eth0 ipv4.gateway '' ipv4.addr '' ipv4.method auto ipv4.may-fail no ipv6.gateway '' ipv6.addresses '' ipv6.method auto ipv6.dns-search test.com ipv6.may-fail no" 0 "Setting eth0 to autoconfiguration"
        # This elaborative change of eth0 connection causes that NetworkManager will receive
        # the exact same address from dhcp that podman assigned to the container. Without this,
        # routing tables that podman creates would not be correct and we would face error during
        # clean up after the container
        rlRun "podman exec $dnsconfd_cid nmcli connection up eth0" 0 "Bringing the connection up"
        # FIXME workaround of NM DAD issue
        rlRun "podman exec $dnsconfd_cid nmcli g reload"
        rlRun "podman stop -t 0 $dhcp4_cid" 0 "Stopping containers"
        rlRun "podman container rm $dhcp4_cid" 0 "Removing containers"
        rlRun "dhcp4_cid=\$(podman run -d --cap-add=NET_RAW --network dnsconfd_network:ip=192.168.6.5,ip=2001:db8::a1 localhost/dnsconfd_utilities:latest dhcp_entry.sh /etc/dhcp/dhcpd-common.conf)" 0 "Starting dhcpd container with dns list"
        rlRun "podman exec $dnsconfd_cid nmcli connection up eth0"
        # FIXME workaround of NM DAD issue
        rlRun "podman exec $dnsconfd_cid nmcli g reload"
        rlRun "podman exec $dnsconfd_cid dnsconfd status --json | jq_filter_general > status1" 0 "Getting status of dnsconfd"
        rlAssertNotDiffer status1 $ORIG_DIR/expected_status.json
        rlRun "podman exec $dnsconfd_cid getent hosts first-address.test.com | grep 192.168.6.3" 0 "Verifying correct address resolution"
        rlRun "podman exec $dnsconfd_cid getent hosts second-address.test.com | grep 192.168.6.4" 0 "Verifying correct address resolution"
        rlRun "podman exec $dnsconfd_cid getent hosts second-address | grep 192.168.6.4" 0 "Verifying correct address resolution"
        rlRun "podman exec $dnsconfd_cid getent hosts third-address.test.com | grep 2001:db8::3" 0 "Verifying correct address resolution"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "podman exec $dnsconfd_cid journalctl -u dnsconfd" 0 "Saving dnsconfd logs"
        rlRun "podman exec $dnsconfd_cid journalctl -u unbound" 0 "Saving unbound logs"
        rlRun "podman exec $dnsconfd_cid ip route" 0 "Saving present routes"
        rlRun "popd"
        rlRun "podman stop -t 0 $dnsconfd_cid $dnsmasq1_cid $dnsmasq2_cid $dnsmasq3_cid $dhcp4_cid $dhcp6_cid" 0 "Stopping containers"
        rlRun "podman container rm $dnsconfd_cid $dnsmasq1_cid $dnsmasq2_cid $dnsmasq3_cid $dhcp4_cid $dhcp6_cid" 0 "Removing containers"
        rlRun "podman network rm dnsconfd_network" 0 "Removing networks"
        rlRun "rm -r $tmp" 0 "Remove tmp directory"
    rlPhaseEnd
rlJournalEnd
