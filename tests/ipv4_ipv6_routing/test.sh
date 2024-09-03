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


        rlRun "podman network create dnsconfd_network1 --internal -d=bridge --gateway=192.168.5.1 --subnet=192.168.5.0/24"

        rlRun "podman network create dnsconfd_network2 --internal -d=bridge --gateway=192.168.6.1 --subnet=192.168.6.0/24"

        rlRun "podman network create dnsconfd_network3 --internal -d=bridge --gateway=2001:db8::1 --subnet=2001:db8::/120"

        rlRun "podman network create dnsconfd_network4 --internal -d=bridge --gateway=2001:db8::101 --subnet=2001:db8::100/120"

        rlRun "podman network create dnsconfd_network5 --internal -d=bridge --gateway=192.168.7.1 --subnet=192.168.7.0/24"

        rlRun "podman network create dnsconfd_network6 --internal -d=bridge --gateway=192.168.8.1 --subnet=192.168.8.0/24"

        rlRun "podman network create dnsconfd_network7 --internal -d=bridge --gateway=2001:db8::201 --subnet=2001:db8::200/120"

        rlRun "podman network create dnsconfd_network8 --internal -d=bridge --gateway=2001:db8::301 --subnet=2001:db8::300/120"



        # dns=none is neccessary, because otherwise resolv.conf is created and
        # mounted by podman as read-only
        rlRun "dnsconfd_cid=\$(podman run -d --dns='none' --cap-add=NET_ADMIN --cap-add=NET_RAW \
                               --network dnsconfd_network1:interface_name=eth0,ip=192.168.5.2 --network dnsconfd_network3:interface_name=eth1,ip=2001:db8::2\
                               --network dnsconfd_network5:interface_name=eth2,ip=192.168.7.2 --network dnsconfd_network7:interface_name=eth3,ip=2001:db8::202\
                               dnsconfd_testing:latest)" 0 "Starting dnsconfd container"

        rlRun "routing1_cid=\$(podman run -d --dns='none' --network dnsconfd_network1:ip=192.168.5.3 --network dnsconfd_network2:ip=192.168.6.2 --cap-add=NET_ADMIN --cap-add=NET_RAW --privileged localhost/dnsconfd_utilities:latest\
               /bin/bash -c 'sleep 10000')" 0 "Starting routing container 1"

        rlRun "dnsmasq1_cid=\$(podman run -d --dns='none' --network dnsconfd_network2:ip=192.168.6.3 localhost/dnsconfd_utilities:latest\
               dnsmasq_entry.sh --listen-address=192.168.6.3 --address=/first-address.test.com/192.168.6.3)" 0 "Starting first dnsmasq container"

        rlRun "routing2_cid=\$(podman run -d --dns='none' --network dnsconfd_network3:ip=2001:db8::3 --network dnsconfd_network4:ip=2001:db8::102 --cap-add=NET_ADMIN --cap-add=NET_RAW --privileged localhost/dnsconfd_utilities:latest\
               /bin/bash -c 'sleep 10000')" 0 "Starting routing container"

        rlRun "dnsmasq2_cid=\$(podman run -d --dns='none' --network dnsconfd_network4:ip=2001:db8::103 localhost/dnsconfd_utilities:latest\
               dnsmasq_entry.sh --listen-address=2001:db8::103 --address=/second-address.test.com/2001:db8::103)" 0 "Starting second dnsmasq container"

        rlRun "routing3_cid=\$(podman run -d --dns='none' --network dnsconfd_network5:ip=192.168.7.3 --network dnsconfd_network6:ip=192.168.8.2 --cap-add=NET_ADMIN --cap-add=NET_RAW --privileged localhost/dnsconfd_utilities:latest\
               /bin/bash -c 'sleep 10000')" 0 "Starting routing container 1"

        rlRun "dnsmasq3_cid=\$(podman run -d --dns='none' --network dnsconfd_network6:ip=192.168.8.3 localhost/dnsconfd_utilities:latest\
               dnsmasq_entry.sh --listen-address=192.168.8.3 --address=/third-address.test.com/192.168.8.3)" 0 "Starting first dnsmasq container"

        rlRun "routing4_cid=\$(podman run -d --dns='none' --network dnsconfd_network7:ip=2001:db8::203 --network dnsconfd_network8:ip=2001:db8::302 --cap-add=NET_ADMIN --cap-add=NET_RAW --privileged localhost/dnsconfd_utilities:latest\
               /bin/bash -c 'sleep 10000')" 0 "Starting routing container"

        rlRun "dnsmasq4_cid=\$(podman run -d --dns='none' --network dnsconfd_network8:ip=2001:db8::303 localhost/dnsconfd_utilities:latest\
               dnsmasq_entry.sh --listen-address=2001:db8::303 --address=/fourth-address.test.com/2001:db8::303)" 0 "Starting second dnsmasq container"

    rlPhaseEnd

    rlPhaseStartTest
        sleep 2
        rlRun "podman exec $routing1_cid /bin/bash -c 'echo 1 > /proc/sys/net/ipv4/ip_forward'" 0 "enable ip forwarding on routing server"
        rlRun "podman exec $routing2_cid /bin/bash -c 'echo 1 > /proc/sys/net/ipv6/conf/all/forwarding'" 0 "enable ip forwarding on routing server"
        rlRun "podman exec $routing3_cid /bin/bash -c 'echo 1 > /proc/sys/net/ipv4/ip_forward'" 0 "enable ip forwarding on routing server"
        rlRun "podman exec $routing4_cid /bin/bash -c 'echo 1 > /proc/sys/net/ipv6/conf/all/forwarding'" 0 "enable ip forwarding on routing server"

        # easier to enable masquerade on both interfaces than to find out which one is connected to the right network
        rlRun "podman exec $routing1_cid iptables -t nat -I POSTROUTING -o eth0 -j MASQUERADE" 0 "enable masquerade on eth0 of routing server"
        rlRun "podman exec $routing1_cid iptables -t nat -I POSTROUTING -o eth1 -j MASQUERADE" 0 "enable masquerade on eth1 of routing server"
        rlRun "podman exec $routing2_cid ip6tables -t nat -I POSTROUTING -o eth0 -j MASQUERADE" 0 "enable masquerade on eth0 of routing server"
        rlRun "podman exec $routing2_cid ip6tables -t nat -I POSTROUTING -o eth1 -j MASQUERADE" 0 "enable masquerade on eth1 of routing server"
        rlRun "podman exec $routing3_cid iptables -t nat -I POSTROUTING -o eth0 -j MASQUERADE" 0 "enable masquerade on eth0 of routing server"
        rlRun "podman exec $routing3_cid iptables -t nat -I POSTROUTING -o eth1 -j MASQUERADE" 0 "enable masquerade on eth1 of routing server"
        rlRun "podman exec $routing4_cid ip6tables -t nat -I POSTROUTING -o eth0 -j MASQUERADE" 0 "enable masquerade on eth0 of routing server"
        rlRun "podman exec $routing4_cid ip6tables -t nat -I POSTROUTING -o eth1 -j MASQUERADE" 0 "enable masquerade on eth1 of routing server"

        sleep 2
        rlRun "podman exec $dnsconfd_cid /bin/bash -c 'nmcli connection mod eth0 ipv4.dns 192.168.6.3 && nmcli connection mod eth0 ipv4.gateway 192.168.5.3'" 0 "Adding dns server to the first NM active profile"
        rlRun "podman exec $dnsconfd_cid /bin/bash -c 'nmcli connection mod eth1 ipv6.dns 2001:db8::103 && nmcli connection mod eth1 ipv6.gateway 2001:db8::3'" 0 "Adding dns server to the second NM active profile"
        rlRun "podman exec $dnsconfd_cid /bin/bash -c 'nmcli connection mod eth2 ipv4.dns 192.168.8.3 && nmcli connection mod eth2 ipv4.gateway 192.168.7.3'" 0 "Adding dns server to the third NM active profile"
        rlRun "podman exec $dnsconfd_cid /bin/bash -c 'nmcli connection mod eth3 ipv6.dns 2001:db8::303 && nmcli connection mod eth3 ipv6.gateway 2001:db8::203'" 0 "Adding dns server to the fourth NM active profile"

        rlRun "podman exec $dnsconfd_cid nmcli connection mod eth0 +ipv4.routes '192.168.122.0/24 10.10.10.10'" 0 "Adding test route"


        rlRun "podman exec $dnsconfd_cid nmcli connection up eth0"
        rlRun "podman exec $dnsconfd_cid nmcli connection up eth1"
        rlRun "podman exec $dnsconfd_cid nmcli connection up eth2"
        rlRun "podman exec $dnsconfd_cid nmcli connection up eth3"
        sleep 5

        rlRun "podman exec $dnsconfd_cid /bin/bash -c 'ip route | grep 192.168.6.3 || ip route | grep 192.168.8.3'" 0 "Verify that route to one of the ipv4 DNS is present"
        rlRun "podman exec $dnsconfd_cid /bin/bash -c 'ip -6 route | grep 2001:db8::103 || ip -6 route | grep 2001:db8::303'" 0 "Verify that route to one of the ipv6 DNS is present"

        rlRun "podman exec $dnsconfd_cid getent hosts first-address.test.com | grep 192.168.6.3" 0 "Verifying correct address resolution"
        rlRun "podman exec $dnsconfd_cid getent hosts second-address.test.com | grep 2001:db8::103" 0 "Verifying correct address resolution"
        rlRun "podman exec $dnsconfd_cid getent hosts third-address.test.com | grep 192.168.8.3" 0 "Verifying correct address resolution"
        rlRun "podman exec $dnsconfd_cid getent hosts fourth-address.test.com | grep 2001:db8::303" 0 "Verifying correct address resolution"

        rlRun "podman exec $dnsconfd_cid ip route | grep 10.10.10.10" 0 "Verify that test route is still present"
        rlRun "podman exec $dnsconfd_cid systemctl stop dnsconfd" 0 "Stop dnsconfd"
        sleep 5
        rlRun "podman exec $dnsconfd_cid ip route | grep 192.168.6.3" 1 "Verify that routes to DNS server was removed"
        rlRun "podman exec $dnsconfd_cid ip route | grep 2001:db8::103" 1 "Verify that routes to DNS server was removed"
        rlRun "podman exec $dnsconfd_cid ip route | grep 192.168.8.3" 1 "Verify that routes to DNS server was removed"
        rlRun "podman exec $dnsconfd_cid ip route | grep 2001:db8::303" 1 "Verify that routes to DNS server was removed"

        rlRun "podman exec $dnsconfd_cid ip route | grep 10.10.10.10" 0 "Verify that test route is still present"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "podman exec $dnsconfd_cid journalctl -u dnsconfd" 0 "Saving dnsconfd logs"
        rlRun "podman exec $dnsconfd_cid journalctl -u unbound" 0 "Saving unbound logs"
        rlRun "podman exec $dnsconfd_cid ip route" 0 "Saving present routes"
        rlRun "popd"
        rlRun "podman stop -t 0 $dnsconfd_cid $routing1_cid $dnsmasq1_cid $routing2_cid $dnsmasq2_cid $routing3_cid $dnsmasq3_cid $routing4_cid $dnsmasq4_cid" 0 "Stopping containers"
        rlRun "podman container rm $dnsconfd_cid $routing1_cid $dnsmasq1_cid $routing2_cid $dnsmasq2_cid $routing3_cid $dnsmasq3_cid $routing4_cid $dnsmasq4_cid" 0 "Removing containers"
        rlRun "podman network rm dnsconfd_network1 dnsconfd_network2 dnsconfd_network3 dnsconfd_network4 dnsconfd_network5 dnsconfd_network6 dnsconfd_network7 dnsconfd_network8" 0 "Removing networks"
        rlRun "rm -r $tmp" 0 "Remove tmp directory"
    rlPhaseEnd
rlJournalEnd
