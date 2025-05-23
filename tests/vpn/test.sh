#!/bin/bash
# vim: dict+=/usr/share/beakerlib/dictionary.vim cpt=.,w,b,u,t,i,k
. /usr/share/beakerlib/beakerlib.sh || exit 1
. ../dnsconfd_helper_functions.sh || exit 1
ORIG_DIR=$(pwd)

VPN_SETTINGS="ca = /etc/openvpn/client/ca.crt, cipher = AES-256-CBC, connection-type = tls, cert = /etc/openvpn/client/dummy.crt, key = /etc/openvpn/client/dummy.key, port = 1194, remote = 192.168.6.30"

rlJournalStart
    rlPhaseStartSetup
        rlRun "tmp=\$(mktemp -d)" 0 "Create tmp directory"
        rlRun "pushd $tmp"
        rlRun "set -o pipefail"
        rlRun "podman network create dnsconfd_network --internal -d=bridge  --gateway=192.168.6.1 --subnet=192.168.6.0/24"
        rlRun "podman network create dnsconfd_network2 --internal -d=bridge --gateway=192.168.7.1 --subnet=192.168.7.0/24"
        # dns=none is neccessary, because otherwise resolv.conf is created and
        # mounted by podman as read-only
        rlRun "dhcp_cid=\$(podman run -d --cap-add=NET_RAW --network dnsconfd_network:ip=192.168.6.20 localhost/dnsconfd_utilities:latest dhcp_entry.sh /etc/dhcp/dhcpd-common.conf)" 0 "Starting dhcpd container"
        rlRun "vpn_cid=\$(podman run -d --cap-add=NET_ADMIN --cap-add=NET_RAW --privileged --security-opt label=disable --device=/dev/net/tun --network dnsconfd_network:ip=192.168.6.30 --network dnsconfd_network2:ip=192.168.7.3 localhost/dnsconfd_utilities:latest vpn_entry.sh)"
        rlRun "dnsconfd_cid=\$(podman run -d --privileged --security-opt label=disable --device=/dev/net/tun --dns='none' --network dnsconfd_network:ip=192.168.6.2 dnsconfd_testing:latest)" 0 "Starting dnsconfd container"
        rlRun "dnsmasq1_cid=\$(podman run -d --dns='none' --network dnsconfd_network:ip=192.168.6.3 localhost/dnsconfd_utilities:latest dnsmasq_entry.sh --listen-address=192.168.6.3 --address=/first-address.test.com/192.168.6.3 --address=/first-address.whatever.com/192.168.6.3)" 0 "Starting first dnsmasq container"
        rlRun "dnsmasq2_cid=\$(podman run -d --dns='none' --network dnsconfd_network:ip=192.168.6.4 localhost/dnsconfd_utilities:latest dnsmasq_entry.sh --listen-address=192.168.6.4 --address=/second-address.test.com/192.168.6.4)" 0 "Starting second dnsmasq container"
        rlRun "dnsmasq3_cid=\$(podman run -d --dns='none' --network dnsconfd_network2:ip=192.168.7.2 localhost/dnsconfd_utilities:latest dnsmasq_entry.sh --listen-address=192.168.7.2 --address=/dummy.vpndomain.com/192.168.6.5 --address=/first-address.whatever.com/192.168.6.5)" 0 "Starting third dnsmasq container"
    rlPhaseEnd

    rlPhaseStartTest
        rlRun "podman exec $vpn_cid /bin/bash -c 'echo 1 > /proc/sys/net/ipv4/ip_forward'" 0 "enable ip forwarding on vpn server"
        # easier to enable this on both than to find out which one is correct
        rlRun "podman exec $vpn_cid nft add table nat" 0 "enable masquerade on eth0 of routing server"
        rlRun "podman exec $vpn_cid nft -- add chain nat prerouting { type nat hook prerouting priority -100 \; }" 0 "enable masquerade on eth0 of routing server"
        rlRun "podman exec $vpn_cid nft add chain nat postrouting { type nat hook postrouting priority 100 \; }" 0 "enable masquerade on eth1 of routing server"
        rlRun "podman exec $vpn_cid nft add rule nat postrouting oifname 'eth0' masquerade" 0 "enable masquerade on eth2 of routing server"
        rlRun "podman exec $vpn_cid nft add rule nat postrouting oifname 'eth1' masquerade" 0 "enable masquerade on eth2 of routing server"
        rlRun "podman exec $dnsconfd_cid systemctl start network-online.target"
        rlRun "podman exec $dnsconfd_cid nmcli connection mod eth0 connection.autoconnect yes ipv4.gateway '' ipv4.addr '' ipv4.method auto ipv6.method disabled" 0 "Setting eth0 to autoconfiguration"
        rlRun "podman exec $dnsconfd_cid nmcli con up eth0"
        # FIXME workaround of NM DAD issue
        rlRun "podman exec $dnsconfd_cid nmcli g reload"
        rlRun "podman exec $dnsconfd_cid dnsconfd status --json | jq_filter_general > status1" 0 "Getting status of dnsconfd"
        rlAssertNotDiffer status1 $ORIG_DIR/expected_status1.json
        rlRun "podman exec $dnsconfd_cid getent hosts first-address.test.com | grep 192.168.6.3" 0 "Verifying correct address resolution"
        rlRun "podman exec $dnsconfd_cid getent hosts second-address.test.com | grep 192.168.6.4" 0 "Verifying correct address resolution"
        rlRun "podman exec $dnsconfd_cid getent hosts second-address | grep 192.168.6.4" 0 "Verifying correct address resolution"
        ### now connect to VPN
        rlRun "podman exec $vpn_cid bash -c 'cd /etc/openvpn/easy-rsa && ./easyrsa --no-pass --batch build-client-full dummy'"
        rlRun "podman cp $vpn_cid:/etc/openvpn/easy-rsa/pki/issued/dummy.crt $dnsconfd_cid:/etc/openvpn/client/dummy.crt"
        rlRun "podman cp $vpn_cid:/etc/openvpn/easy-rsa/pki/private/dummy.key $dnsconfd_cid:/etc/openvpn/client/dummy.key"
        rlRun "podman cp $vpn_cid:/etc/openvpn/easy-rsa/pki/ca.crt $dnsconfd_cid:/etc/openvpn/client/ca.crt"
        rlRun "podman exec $dnsconfd_cid nmcli connection add type vpn vpn-type openvpn ipv4.method auto ipv4.never-default yes vpn.data '$VPN_SETTINGS'" 0 "Creating vpn connection"
        rlRun "podman exec $dnsconfd_cid nmcli connection up vpn" 0 "Connecting to vpn"
        # FIXME workaround of NM DAD issue
        rlRun "podman exec $dnsconfd_cid nmcli g reload"
        rlRun "podman exec $dnsconfd_cid dnsconfd status --json | jq_filter_general > status2" 0 "Getting status of dnsconfd"
        rlAssertNotDiffer status2 $ORIG_DIR/expected_status2.json
        rlRun "podman exec $dnsconfd_cid getent hosts dummy | grep 192.168.6.5" 0 "Verifying correct address resolution"
        rlRun "podman exec $dnsconfd_cid getent hosts second-address | grep 192.168.6.4" 0 "Verifying correct address resolution"
        if rlTestVersion "$(rpm -q --queryformat '%{VERSION}' dnsconfd)" ">=" "1.7.3" && rlTestVersion "$(rpm -q --queryformat '%{VERSION}' NetworkManager)" ">=" "1.54"; then
          # fix for this behavior has been implemented in dnsconfd 1.7.3 and NM > 1.53.3
          rlRun "podman exec $dnsconfd_cid nmcli connection down vpn" 0 "Disconnecting from vpn"
          rlRun "podman exec $dnsconfd_cid nmcli connection mod vpn ipv4.never-default no" 0 "Allowing vpn to have gateway"
          rlRun "podman exec $dnsconfd_cid nmcli connection up vpn" 0 "Connecting to vpn"
          # FIXME workaround of NM DAD issue
          rlRun "podman exec $dnsconfd_cid nmcli g reload"
          rlRun "podman exec $dnsconfd_cid dnsconfd status --json | jq_filter_general > status3" 0 "Getting status of dnsconfd"
          rlAssertNotDiffer status3 $ORIG_DIR/expected_status3.json
          rlRun "podman exec $dnsconfd_cid getent hosts first-address.whatever.com | grep 192.168.6.5" 0 "Verifying correct address resolution"
          rlRun "podman exec $dnsconfd_cid getent hosts first-address.test.com | grep 192.168.6.3" 0 "Verifying correct address resolution"
          rlRun "podman exec $dnsconfd_cid getent hosts second-address.test.com | grep 192.168.6.4" 0 "Verifying correct address resolution"
          rlRun "podman exec $dnsconfd_cid getent hosts dummy.vpndomain.com | grep 192.168.6.5" 0 "Verifying correct address resolution"
        fi
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "podman exec $dnsconfd_cid journalctl -u dnsconfd" 0 "Saving dnsconfd logs"
        rlRun "podman exec $dnsconfd_cid journalctl -u unbound" 0 "Saving unbound logs"
        rlRun "podman exec $dnsconfd_cid journalctl -u NetworkManager" 0 "Saving nm logs"
        rlRun "podman exec $dnsconfd_cid ip route" 0 "Saving present routes"
        rlRun "popd"
        rlRun "podman stop -t 0 $dnsconfd_cid $dnsmasq1_cid $dnsmasq2_cid $dnsmasq3_cid $dhcp_cid $vpn_cid" 0 "Stopping containers"
        rlRun "podman container rm $dnsconfd_cid $dnsmasq1_cid $dnsmasq2_cid $dnsmasq3_cid $dhcp_cid $vpn_cid" 0 "Removing containers"
        rlRun "podman network rm dnsconfd_network dnsconfd_network2" 0 "Removing networks"
        rlRun "rm -r $tmp" 0 "Remove tmp directory"
    rlPhaseEnd
rlJournalEnd
