#!/bin/bash
# vim: dict+=/usr/share/beakerlib/dictionary.vim cpt=.,w,b,u,t,i,k
. /usr/share/beakerlib/beakerlib.sh || exit 1
. ../dnsconfd_helper_functions.sh || exit 1
ORIG_DIR=$(pwd)

rlJournalStart
    rlPhaseStartSetup
        rlRun "tmp=\$(mktemp -d)" 0 "Create tmp directory"
        rlRun "cp ./ca_cert.pem ./ca_cert2.pem $tmp" 0 "Copying CA certificate"
        rlRun "pushd $tmp"
        rlRun "set -o pipefail"
        rlRun "podman network create dnsconfd_network --internal -d=bridge --gateway=192.168.6.1 --subnet=192.168.6.0/24"
        # dns=none is neccessary, because otherwise resolv.conf is created and
        # mounted by podman as read-only
        rlRun "dnsconfd_cid=\$(podman run -d --privileged --dns='none' --network dnsconfd_network:ip=192.168.6.2 dnsconfd_testing:latest)" 0 "Starting dnsconfd container"
        rlRun "bind_cid=\$(podman run -d --dns='none' --network dnsconfd_network:ip=192.168.6.3 localhost/dnsconfd_utilities:latest bind_entry.sh /etc/named.conf)" 0 "Starting dnsmasq container"
    rlPhaseEnd

    rlPhaseStartTest
        rlRun "podman cp ca_cert.pem $dnsconfd_cid://etc/pki/ca-trust/source/anchors/ca_cert.pem" 0 "Installing CA"
        rlRun "podman exec $dnsconfd_cid update-ca-trust extract" 0 "updating CA trust"
        # this is necessary, because if ca trust is not in place before unbound start then verification of
        # server certificate fails
        rlRun "podman exec $dnsconfd_cid systemctl restart unbound"
        rlRun "podman exec $dnsconfd_cid nmcli connection mod eth0 ipv4.dns dns+tls://192.168.6.3#named" 0 "Adding dns server to NM active profile"
        # we have to restart, otherwise NM will attempt to change ipv6 and because it has no permissions, it will fail
        rlRun "podman exec $dnsconfd_cid nmcli connection up eth0" 0 "Bringing the connection up"
        # FIXME workaround of NM DAD issue
        rlRun "podman exec $dnsconfd_cid nmcli g reload"
        rlRun "podman exec $dnsconfd_cid dnsconfd status --json | jq_filter_general > status1" 0 "Getting status of dnsconfd"
        rlAssertNotDiffer status1 $ORIG_DIR/expected_status.json
        rlRun "podman exec $dnsconfd_cid getent hosts server.example.com | grep 192.168.6.5" 0 "Verifying correct address resolution"
        # custom CA testing
        rlRun "podman stop -t 0 $bind_cid" 0 "Stopping bind"
        rlRun "podman container rm $bind_cid" 0 "Removing containers"
        rlRun "bind_cid=\$(podman run -d --dns='none' --network dnsconfd_network:ip=192.168.6.3 localhost/dnsconfd_utilities:latest bind_entry.sh /etc/named2.conf)" 0 "Starting dnsmasq container"
        rlRun "podman exec $dnsconfd_cid mkdir -p /etc/pki/dns/extracted/pem" 0 "Create dns CA directory"
        rlRun "podman exec $dnsconfd_cid rm /etc/pki/ca-trust/source/anchors/ca_cert.pem" 0 "Move certificate"
        rlRun "podman cp ca_cert2.pem $dnsconfd_cid://etc/pki/dns/extracted/pem/tls-ca-bundle.pem"
        rlRun "podman exec $dnsconfd_cid update-ca-trust extract" 0 "Rebuild global store without custom certificate"
        rlRun "podman exec $dnsconfd_cid /bin/bash -c 'printf \"[global-dns]\\n[global-dns-domain-*]\\nservers=dns+tls://192.168.6.3#named2\\n\" >> /etc/NetworkManager/conf.d/dnsconfd.conf'"
        rlRun "podman exec $dnsconfd_cid nmcli connection mod eth0 ipv4.dns ''" 0 "Removing dns server from NM active profile"
        rlRun "podman exec $dnsconfd_cid nmcli connection up eth0" 0 "Bringing the connection up"
        # after this update, Dnsconfd should recognize that the higher priority CA bundle
        # is now present and it should be used
        # FIXME workaround of NM DAD issue
        rlRun "podman exec $dnsconfd_cid nmcli g reload" 0 "Reloading NetworkManager"
        rlRun "podman exec $dnsconfd_cid getent hosts server.example.com | grep 192.168.6.5" 0 "Verifying correct address resolution"
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
