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
        rlRun "podman network create dnsconfd_network1 --internal -d=bridge --gateway=192.168.5.1 --subnet=192.168.5.0/24"
        rlRun "podman network create dnsconfd_network2 --internal -d=bridge --gateway=192.168.6.1 --subnet=192.168.6.0/24"
        rlRun "podman network create dnsconfd_network3 --internal -d=bridge --gateway=192.168.7.1 --subnet=192.168.7.0/24"
        # dns=none is neccessary, because otherwise resolv.conf is created and
        # mounted by podman as read-only
        rlRun "dnsconfd_cid=\$(podman run -d --dns='none' --privileged --network dnsconfd_network1:interface_name=eth0,ip=192.168.5.2 --network dnsconfd_network2:interface_name=eth1,ip=192.168.6.2 dnsconfd_testing:latest)" 0 "Starting dnsconfd container"
        rlRun "dnsmasq_cid=\$(podman run -d --dns='none' --network dnsconfd_network3:ip=192.168.7.4 localhost/dnsconfd_utilities:latest dnsmasq_entry.sh --listen-address=192.168.7.4 --address=/address.test.com/192.168.7.4)" 0 "Starting dnsmasq container"
        rlRun "routing1_cid=\$(podman run -d --dns='none' --network dnsconfd_network1:ip=192.168.5.3 --network dnsconfd_network2:ip=192.168.6.3 --network dnsconfd_network3:ip=192.168.7.3 --cap-add=NET_ADMIN --cap-add=NET_RAW --privileged localhost/dnsconfd_utilities:latest\
       /bin/bash -c 'sleep 10000')" 0 "Starting routing container 1"
    rlPhaseEnd

    rlPhaseStartTest
        rlRun "podman exec $dnsconfd_cid systemctl start network-online.target"
        rlRun "podman exec $routing1_cid /bin/bash -c 'echo 1 > /proc/sys/net/ipv4/ip_forward'" 0 "enable ip forwarding on routing server"
        rlRun "podman exec $routing1_cid nft add table nat" 0 "enable masquerade on eth0 of routing server"
        rlRun "podman exec $routing1_cid nft -- add chain nat prerouting { type nat hook prerouting priority -100 \; }" 0 "enable masquerade on eth0 of routing server"
        rlRun "podman exec $routing1_cid nft add chain nat postrouting { type nat hook postrouting priority 100 \; }" 0 "enable masquerade on eth1 of routing server"
        rlRun "podman exec $routing1_cid nft add rule nat postrouting oifname 'eth0' masquerade" 0 "enable masquerade on eth2 of routing server"
        rlRun "podman exec $routing1_cid nft add rule nat postrouting oifname 'eth1' masquerade" 0 "enable masquerade on eth2 of routing server"
        rlRun "podman exec $routing1_cid nft add rule nat postrouting oifname 'eth2' masquerade" 0 "enable masquerade on eth2 of routing server"
        rlRun "podman exec $dnsconfd_cid /bin/bash -c 'nmcli con mod eth0 ipv4.dns 192.168.7.4 && nmcli con mod eth0 ipv4.gateway 192.168.5.3'" 0 "Adding dns server to NM active profile"
        rlRun "podman exec $dnsconfd_cid /bin/bash -c 'nmcli con mod eth1 ipv4.dns 192.168.7.4 && nmcli con mod eth1 ipv4.gateway 192.168.6.3'" 0 "Adding dns server to NM active profile"
        rlRun "podman exec $dnsconfd_cid nmcli con up eth0"
        rlRun "podman exec $dnsconfd_cid nmcli con up eth1"
        # FIXME workaround of NM DAD issue
        rlRun "podman exec $dnsconfd_cid nmcli g reload"
        rlRun "podman exec $dnsconfd_cid dnsconfd status --json | jq_filter_general > status1" 0 "Getting status of dnsconfd"
        rlAssertNotDiffer status1 $ORIG_DIR/expected_status.json
        rlRun "podman exec $dnsconfd_cid getent hosts address.test.com | grep 192.168.7.4" 0 "Verifying correct address resolution"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "podman exec $dnsconfd_cid journalctl -u dnsconfd" 0 "Saving dnsconfd logs"
        rlRun "podman exec $dnsconfd_cid journalctl -u unbound" 0 "Saving unbound logs"
        rlRun "podman exec $dnsconfd_cid ip route" 0 "Saving present routes"
        rlRun "popd"
        rlRun "podman stop -t 0 $dnsconfd_cid $dnsmasq_cid $routing1_cid" 0 "Stopping containers"
        rlRun "podman container rm $dnsconfd_cid $dnsmasq_cid $routing1_cid" 0 "Removing containers"
        rlRun "podman network rm dnsconfd_network1 dnsconfd_network2 dnsconfd_network3" 0 "Removing networks"
        rlRun "rm -r $tmp" 0 "Remove tmp directory"
    rlPhaseEnd
rlJournalEnd
