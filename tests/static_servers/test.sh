#!/bin/bash
# vim: dict+=/usr/share/beakerlib/dictionary.vim cpt=.,w,b,u,t,i,k
. /usr/share/beakerlib/beakerlib.sh || exit 1
DBUS_NAME=org.freedesktop.resolve1
ORIG_DIR=$(pwd)

rlJournalStart
    rlPhaseStartSetup
        rlRun "tmp=\$(mktemp -d)" 0 "Create tmp directory"
        rlRun "cp ./ca_cert.pem $tmp/ca_cert.pem" 0 "Copying CA certificate"
        rlRun "cp ./dnsconfd.conf $tmp/dnsconfd.conf" 0 "Copying config file"
        rlRun "cp ./dnsconfd-wrong.conf $tmp/dnsconfd-wrong.conf" 0 "Copying wrong config file"
        rlRun "cp ./dnsconfd-second.conf $tmp/dnsconfd-second.conf" 0 "Copying config file"
        rlRun "pushd $tmp"
        rlRun "podman network create dnsconfd_network --internal -d=bridge --gateway=192.168.6.1 --subnet=192.168.6.0/24"
        # dns=none is neccessary, because otherwise resolv.conf is created and
        # mounted by podman as read-only
        rlRun "dnsconfd_cid=\$(podman run -d --dns='none' --network dnsconfd_network:ip=192.168.6.2 dnsconfd_testing:latest)" 0 "Starting dnsconfd container"
        rlRun "bind_cid=\$(podman run -d --dns='none' --network dnsconfd_network:ip=192.168.6.3 localhost/dnsconfd_utilities:latest bind_entry.sh)" 0 "Starting dnsmasq container"

        rlRun "dnsmasq1_cid=\$(podman run -d --dns='none' --network dnsconfd_network:ip=192.168.6.10 localhost/dnsconfd_utilities:latest\
               dnsmasq_entry.sh --listen-address=192.168.6.10 --address=/first-address.test.com/192.168.6.10)" 0 "Starting first dnsmasq container"
        rlRun "dnsmasq2_cid=\$(podman run -d --dns='none' --network dnsconfd_network:ip=192.168.6.20 localhost/dnsconfd_utilities:latest\
               dnsmasq_entry.sh --listen-address=192.168.6.20 --address=/second-address.testdomain.com/192.168.6.20)" 0 "Starting second dnsmasq container"
        rlRun "dnsmasq3_cid=\$(podman run -d --dns='none' --network dnsconfd_network:ip=192.168.6.30 localhost/dnsconfd_utilities:latest\
               dnsmasq_entry.sh --listen-address=192.168.6.30 --address=/third-address.second-domain.com/192.168.6.30)" 0 "Starting second dnsmasq container"
    rlPhaseEnd

    rlPhaseStartTest
        rlRun "podman cp dnsconfd.conf $dnsconfd_cid://etc/dnsconfd.conf"
        rlRun "podman cp ca_cert.pem $dnsconfd_cid://etc/pki/ca-trust/source/anchors/ca_cert.pem" 0 "Installing CA"
        rlRun "podman exec $dnsconfd_cid update-ca-trust extract" 0 "updating CA trust"
        # this is necessary, because if ca trust is not in place before unbound start then verification of
        # server certificate fails
        # and we need new configuration
        rlRun "podman exec $dnsconfd_cid systemctl restart dnsconfd"
        sleep 5
        rlRun "podman exec $dnsconfd_cid dnsconfd --dbus-name=$DBUS_NAME status --json > status1" 0 "Getting status of dnsconfd"
        rlAssertNotDiffer status1 $ORIG_DIR/expected_status.json
        rlRun "podman exec $dnsconfd_cid getent hosts server.example.com | grep 192.168.6.5" 0 "Verifying correct address resolution"
        rlRun "podman cp dnsconfd-wrong.conf $dnsconfd_cid://etc/dnsconfd.conf"
        rlRun "podman exec $dnsconfd_cid systemctl restart dnsconfd" 1 "restart dnsconfd"
        sleep 2
        rlRun "podman exec $dnsconfd_cid systemctl status dnsconfd | grep 'status=13'" 0 "Verify that dnsconfd refused bad option"
        rlRun "podman cp dnsconfd-second.conf $dnsconfd_cid://etc/dnsconfd.conf"
        rlRun "podman exec $dnsconfd_cid systemctl restart dnsconfd" 0 "restart dnsconfd"
        rlRun "podman exec $dnsconfd_cid /bin/bash -c 'nmcli connection mod eth0 ipv4.dns-search testdomain.com && nmcli connection mod eth0 ipv4.dns 192.168.6.20'" 0 "Adding dns server to the NM active profile"
        rlRun "podman exec $dnsconfd_cid systemctl restart NetworkManager" 0 "Reactivating connection"
        sleep 5
        rlRun "podman exec $dnsconfd_cid getent hosts first-address.test.com | grep 192.168.6.10" 0 "Verifying correct address resolution"
        rlRun "podman exec $dnsconfd_cid getent hosts second-address.testdomain.com | grep 192.168.6.20" 0 "Verifying correct address resolution"
        rlRun "podman exec $dnsconfd_cid getent hosts third-address.second-domain.com | grep 192.168.6.30" 0 "Verifying correct address resolution"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "podman exec $dnsconfd_cid journalctl -u dnsconfd" 0 "Saving dnsconfd logs"
        rlRun "podman exec $dnsconfd_cid journalctl -u unbound" 0 "Saving unbound logs"
        rlRun "podman exec $dnsconfd_cid ip route" 0 "Saving present routes"
        rlRun "popd"
        rlRun "podman stop -t 0 $dnsconfd_cid $bind_cid $dnsmasq1_cid $dnsmasq2_cid $dnsmasq3_cid" 0 "Stopping containers"
        rlRun "podman container rm $dnsconfd_cid $bind_cid $dnsmasq1_cid $dnsmasq2_cid $dnsmasq3_cid" 0 "Removing containers"
        rlRun "podman network rm dnsconfd_network" 0 "Removing networks"
        rlRun "rm -r $tmp" 0 "Remove tmp directory"
    rlPhaseEnd
rlJournalEnd
