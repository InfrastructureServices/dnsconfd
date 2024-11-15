#!/bin/bash
# vim: dict+=/usr/share/beakerlib/dictionary.vim cpt=.,w,b,u,t,i,k
. /usr/share/beakerlib/beakerlib.sh || exit 1
. ../dnsconfd_helper_functions.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "tmp=\$(mktemp -d)" 0 "Create tmp directory"
        rlRun "pushd $tmp"
        rlRun "set -o pipefail"
        rlRun "podman network create dnsconfd_network --internal -d=bridge --gateway=192.168.6.1 --subnet=192.168.6.0/24"
        rlRun "podman network create dnsconfd_network2 --internal -d=bridge --gateway=192.168.7.1 --subnet=192.168.7.0/24"
        # dns=none is neccessary, because otherwise resolv.conf is created and
        # mounted by podman as read-only
        rlRun "dnsconfd_cid=\$(podman run -d --dns='none' --privileged --network dnsconfd_network:interface_name=eth0,ip=192.168.6.2 --network dnsconfd_network2:interface_name=eth1,ip=192.168.7.2 dnsconfd_testing:latest)" 0 "Starting dnsconfd container"
        rlRun "dnsmasq_cid=\$(podman run -d --dns='none' --network dnsconfd_network:ip=192.168.6.3 localhost/dnsconfd_utilities:latest dnsmasq_entry.sh --listen-address=192.168.6.3 --address=/address.test.com/192.168.6.3)" 0 "Starting dnsmasq container"
        rlRun "dnsmasq_cid2=\$(podman run -d --dns='none' --network dnsconfd_network2:ip=192.168.7.3 localhost/dnsconfd_utilities:latest dnsmasq_entry.sh --listen-address=192.168.7.3 --address=/address2.xn--oka-eqab.org/192.168.7.3)" 0 "Starting dnsmasq container"
    rlPhaseEnd

    rlPhaseStartTest
        sleep 2
        rlRun "podman exec $dnsconfd_cid nmcli connection mod eth0 ipv4.dns 192.168.6.3" 0 "Adding dns server to NM active profile"
        rlRun "podman exec $dnsconfd_cid /bin/bash -c 'nmcli connection mod eth1 ipv4.dns 192.168.7.3 && nmcli connection mod eth1 ipv4.dns-search čočka.org'" 0 "Adding dns server to NM active profile"
        rlRun "podman exec $dnsconfd_cid systemctl restart NetworkManager"
        sleep 2
        rlRun "podman exec $dnsconfd_cid getent ahosts address.test.com | grep 192.168.6.3" 0 "Verifying correct address resolution"
        rlRun "podman exec $dnsconfd_cid /bin/bash -c 'export LC_ALL=C.UTF-8; getent ahosts address2.čočka.org | grep 192.168.7.3'" 0 "Verifying correct address resolution"
        # new api testing
        rlRun "podman exec $dnsconfd_cid /bin/bash -c 'echo api_choice: dnsconfd >> /etc/dnsconfd.conf'" 0 "switching API"
        rlRun "podman exec $dnsconfd_cid systemctl restart dnsconfd" 0 "restarting dnsconfd"
        sleep 2
        rlRun "podman exec $dnsconfd_cid dnsconfd update 'dns+udp://192.168.6.3' 'dns+udp://192.168.7.3?domain=%C4%8Do%C4%8Dka.org'" 0 "submit update"
        sleep 2
        rlRun "podman exec $dnsconfd_cid getent ahosts address.test.com | grep 192.168.6.3" 0 "Verifying correct address resolution"
        rlRun "podman exec $dnsconfd_cid /bin/bash -c 'export LC_ALL=C.UTF-8; getent ahosts address2.čočka.org | grep 192.168.7.3'" 0 "Verifying correct address resolution"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "podman exec $dnsconfd_cid journalctl -u dnsconfd" 0 "Saving dnsconfd logs"
        rlRun "podman exec $dnsconfd_cid journalctl -u unbound" 0 "Saving unbound logs"
        rlRun "podman exec $dnsconfd_cid ip route" 0 "Saving present routes"
        rlRun "popd"
        rlRun "podman stop -t 0 $dnsconfd_cid $dnsmasq_cid $dnsmasq_cid2" 0 "Stopping containers"
        rlRun "podman container rm $dnsconfd_cid $dnsmasq_cid $dnsmasq_cid2" 0 "Removing containers"
        rlRun "podman network rm dnsconfd_network dnsconfd_network2" 0 "Removing networks"
        rlRun "rm -r $tmp" 0 "Remove tmp directory"
    rlPhaseEnd
rlJournalEnd
