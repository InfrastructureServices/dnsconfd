#!/bin/bash
# vim: dict+=/usr/share/beakerlib/dictionary.vim cpt=.,w,b,u,t,i,k
. /usr/share/beakerlib/beakerlib.sh || exit 1
DBUS_NAME=org.freedesktop.resolve1

VPN_SETTINGS="ca = /etc/openvpn/client/ca.crt, cipher = AES-256-CBC, connection-type = tls, cert = /etc/openvpn/client/dummy.crt, key = /etc/openvpn/client/dummy.key, port = 1194, remote = 192.168.6.30"

rlJournalStart
    rlPhaseStartSetup
        rlRun "tmp=\$(mktemp -d)" 0 "Create tmp directory"
        rlRun "cp expected_status*.json $tmp"
        rlRun "pushd $tmp"
        rlRun "set -o pipefail"
        rlRun "podman network create dnsconfd_network -d=bridge --gateway=192.168.6.1 --subnet=192.168.6.0/24"
        # dns=none is neccessary, because otherwise resolv.conf is created and
        # mounted by podman as read-only
        rlRun "dhcp_cid=\$(podman run -d --cap-add=NET_RAW --network dnsconfd_network:ip=192.168.6.20 dnsconfd_dhcp:latest)" 0 "Starting dhcpd container"
        # unfortunately, vpn needs to access the tun device so the easiest way to achieve this is to run
        # the container as privileged
        rlRun "vpn_cid=\$(podman run -d --privileged --network dnsconfd_network:ip=192.168.6.30 dnsconfd_vpn:latest)"
        sleep 2
        rlRun "dnsconfd_cid=\$(podman run -d --privileged --dns='none' --network dnsconfd_network:ip=192.168.6.2 dnsconfd_testing:latest)" 0 "Starting dnsconfd container"
        rlRun "dnsmasq1_cid=\$(podman run -d --dns='none' --network dnsconfd_network:ip=192.168.6.3 dnsconfd_dnsmasq:latest --listen-address=192.168.6.3 --address=/first-address.test.com/192.168.6.3)" 0 "Starting first dnsmasq container"
        rlRun "dnsmasq2_cid=\$(podman run -d --dns='none' --network dnsconfd_network:ip=192.168.6.4 dnsconfd_dnsmasq:latest --listen-address=192.168.6.4 --address=/second-address.test.com/192.168.6.4)" 0 "Starting second dnsmasq container"
        rlRun "dnsmasq3_cid=\$(podman run -d --dns='none' --network dnsconfd_network:ip=192.168.6.5 dnsconfd_dnsmasq:latest --listen-address=192.168.6.5 --address=/dummy.vpndomain.com/192.168.6.5)" 0 "Starting third dnsmasq container"
    rlPhaseEnd

    rlPhaseStartTest
        sleep 3
        rlRun "podman exec $dnsconfd_cid nmcli connection mod eth0 connection.autoconnect yes ipv4.gateway '' ipv4.addr '' ipv4.method auto" 0 "Setting eth0 to autoconfiguration"
        sleep 5
        rlRun "podman exec $dnsconfd_cid dnsconfd --dbus-name=$DBUS_NAME -s > status1" 0 "Getting status of dnsconfd"
        # in this test we are verifying that the DNS of non-wireless interface has higher priority
        # than the wireless one
        rlAssertNotDiffer status1 expected_status1.json
        rlRun "podman exec $dnsconfd_cid getent hosts first-address.test.com | grep 192.168.6.3" 0 "Verifying correct address resolution"
        rlRun "podman exec $dnsconfd_cid getent hosts second-address.test.com | grep 192.168.6.4" 0 "Verifying correct address resolution"
        rlRun "podman exec $dnsconfd_cid getent hosts second-address | grep 192.168.6.4" 0 "Verifying correct address resolution"
        ### now connect to VPN
        rlRun "podman exec $vpn_cid bash -c 'cd /etc/openvpn/easy-rsa && ./easyrsa --no-pass --batch build-client-full dummy'"
        rlRun "podman cp $vpn_cid:/etc/openvpn/easy-rsa/pki/issued/dummy.crt $dnsconfd_cid:/etc/openvpn/client/dummy.crt"
        rlRun "podman cp $vpn_cid:/etc/openvpn/easy-rsa/pki/private/dummy.key $dnsconfd_cid:/etc/openvpn/client/dummy.key"
        rlRun "podman cp $vpn_cid:/etc/openvpn/keys/ca.crt $dnsconfd_cid:/etc/openvpn/client/ca.crt"
        rlRun "podman exec $dnsconfd_cid nmcli connection add type vpn vpn-type openvpn ipv4.method auto ipv4.never-default yes vpn.data '$VPN_SETTINGS'" 0 "Creating vpn connection"
        rlRun "podman exec $dnsconfd_cid nmcli connection up vpn" 0 "Connecting to vpn"
        sleep 3
        rlRun "podman exec $dnsconfd_cid dnsconfd --dbus-name=$DBUS_NAME -s > status2" 0 "Getting status of dnsconfd"
        rlAssertNotDiffer status2 expected_status2.json
        rlRun "podman exec $dnsconfd_cid getent hosts dummy | grep 192.168.6.5" 0 "Verifying correct address resolution"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "podman stop $dnsconfd_cid $dnsmasq1_cid $dnsmasq2_cid $dnsmasq3_cid $dhcp_cid $vpn_cid" 0 "Stopping containers"
        rlRun "podman container rm $dnsconfd_cid $dnsmasq1_cid $dnsmasq2_cid $dnsmasq3_cid $dhcp_cid $vpn_cid" 0 "Removing containers"
        rlRun "podman network rm dnsconfd_network" 0 "Removing networks"
        rlRun "rm -r $tmp" 0 "Remove tmp directory"
    rlPhaseEnd
rlJournalEnd
