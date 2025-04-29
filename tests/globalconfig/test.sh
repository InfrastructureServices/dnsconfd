#!/bin/bash
# vim: dict+=/usr/share/beakerlib/dictionary.vim cpt=.,w,b,u,t,i,k
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "tmp=\$(mktemp -d)" 0 "Create tmp directory"
        rlRun "cp ./ca_cert.pem $tmp/ca_cert.pem" 0 "Copying CA certificate"
        rlRun "pushd $tmp"
        rlRun "set -o pipefail"
        rlRun "podman network create dnsconfd_network --internal -d=bridge --gateway=192.168.6.1 --subnet=192.168.6.0/24"
        # dns=none is neccessary, because otherwise resolv.conf is created and
        # mounted by podman as read-only
        rlRun "dnsconfd_cid=\$(podman run --privileged -d --dns='none' --privileged --network dnsconfd_network:ip=192.168.6.2 dnsconfd_testing:latest)" 0 "Starting dnsconfd container"
        rlRun "bind_cid=\$(podman run -d --dns='none' --network dnsconfd_network:ip=192.168.6.3 localhost/dnsconfd_utilities:latest bind_entry.sh /etc/named.conf)" 0 "Starting dnsmasq container"
    rlPhaseEnd

    rlPhaseStartTest
        rlRun "podman exec $dnsconfd_cid systemctl start network-online.target"
        rlRun "podman exec $dnsconfd_cid ip route add 0.0.0.0/0 via 192.168.6.1" 0 "Add gateway so the attempts can be logged"
        rlRun "podman exec $dnsconfd_cid /bin/bash -c 'tcpdump -nn -i eth0 \"not host 192.168.6.3 and (port 853 or port 53 or port 453)\" > /tcpdumplog.txt' &" 0 "starting tcpdump"
        rlRun "podman cp ca_cert.pem $dnsconfd_cid://etc/pki/ca-trust/source/anchors/ca_cert.pem" 0 "Installing CA"
        rlRun "podman exec $dnsconfd_cid update-ca-trust extract" 0 "updating CA trust"
        rlRun "podman exec $dnsconfd_cid systemctl restart dnsconfd" 0 "restarting dnsconfd"
        rlRun "podman exec $dnsconfd_cid getent hosts server.example.com | grep 192.168.6.5" 1 "Verifying no result"
        rlRun "podman exec $dnsconfd_cid /bin/bash -c 'printf \"[global-dns-domain-*]\\nservers=dns+tls://192.168.6.3#named\\n\" >> /etc/NetworkManager/conf.d/dnsconfd.conf'"
        rlRun "podman exec $dnsconfd_cid nmcli g reload" 0 "Reload NM"
        rlRun "podman exec $dnsconfd_cid getent hosts server.example.com | grep 192.168.6.5" 0 "Verifying correct resolution"
        sleep 3
        rlRun "podman exec $dnsconfd_cid pkill tcpdump" 0 "Killing tcpdump"
        rlRun "podman exec $dnsconfd_cid find ./tcpdumplog.txt -size 1 | grep tcpdump" 0 "Verify no attempt to contact other DNS server was made"
        rlRun "podman exec $dnsconfd_cid cat /tcpdumplog.txt"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "podman exec $dnsconfd_cid journalctl -u dnsconfd" 0 "Saving dnsconfd logs"
        rlRun "podman exec $dnsconfd_cid journalctl -u unbound" 0 "Saving unbound logs"
        rlRun "podman exec $dnsconfd_cid ip route" 0 "Saving present routes"
        rlRun "popd"
        rlRun "podman stop -t 0 $dnsconfd_cid $bind_cid" 0 "Stopping containers"
        rlRun "podman container rm $dnsconfd_cid $bind_cid" 0 "Removing containers"
        rlRun "podman network rm dnsconfd_network" 0 "Removing networks"
        rlRun "rm -r $tmp" 0 "Remove tmp directory"
    rlPhaseEnd
rlJournalEnd
