#!/bin/bash
# vim: dict+=/usr/share/beakerlib/dictionary.vim cpt=.,w,b,u,t,i,k
. /usr/share/beakerlib/beakerlib.sh || exit 1
. ../dnsconfd_helper_functions.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "podman network create dnsconfd_network --internal -d=bridge --gateway=192.168.6.1 --subnet=192.168.6.0/24"
        rlRun "dnsconfd_cid=\$(podman run --privileged -d --dns='none' --network dnsconfd_network:ip=192.168.6.2 dnsconfd_testing:latest)" 0 "Starting dnsconfd container"
        rlRun "bind_cid=\$(podman run -d --dns='none' --network dnsconfd_network:ip=192.168.6.3 localhost/dnsconfd_utilities:latest /usr/sbin/named -u named -g -d 5 -c /etc/named.conf)" 0 "Starting BIND container with RPZ zone"
        rlRun "dnsmasq_cid=\$(podman run -d --dns='none' --network dnsconfd_network:ip=192.168.6.10 localhost/dnsconfd_utilities:latest\
               dnsmasq_entry.sh --listen-address=192.168.6.10 --address=/address.test.com/192.168.6.10 --address=/blocked.test.com/192.168.6.10)" 0 "Starting dnsmasq container"
        rlRun "podman cp ./rpz_snippet.conf $dnsconfd_cid:/etc/dnsconfd/conf.d/rpz_snippet.conf" 0 "Copying RPZ snippet into snippet directory"
    rlPhaseEnd

    rlPhaseStartTest "RPZ via directory include"
        rlRun "podman cp ./dnsconfd_dir_include.conf $dnsconfd_cid:/etc/dnsconfd/dnsconfd.conf" 0 "Copying directory include config"
        rlRun "podman exec $dnsconfd_cid systemctl restart dnsconfd" 0 "Restarting dnsconfd"
        rlRun "podman exec $dnsconfd_cid nmcli connection mod eth0 ipv4.dns 192.168.6.10" 0 "Adding dns server to NM active profile"
        rlRun "podman exec $dnsconfd_cid nmcli connection up eth0" 0 "Bringing the connection up"
        rlRun "poll_cmd 15 'podman exec $dnsconfd_cid dig blocked.test.com | grep NXDOMAIN'" 0 "Waiting for RPZ zone transfer to complete"
        rlRun "podman exec $dnsconfd_cid getent hosts address.test.com | grep 192.168.6.10" 0 "Verifying non-blocked address resolves"
        rlRun "podman exec $dnsconfd_cid getent hosts blocked.test.com | grep 192.168.6.10" 1 "Verifying RPZ-blocked address does not resolve"
        rlRun "podman exec $dnsconfd_cid dig blocked.test.com | grep NXDOMAIN" 0 "Verifying RPZ returns NXDOMAIN for blocked domain"
    rlPhaseEnd

    rlPhaseStartTest "RPZ via single file include"
        rlRun "podman cp ./dnsconfd_file_include.conf $dnsconfd_cid:/etc/dnsconfd/dnsconfd.conf" 0 "Copying file include config"
        rlRun "podman exec $dnsconfd_cid systemctl restart dnsconfd" 0 "Restarting dnsconfd"
        rlRun "podman exec $dnsconfd_cid nmcli connection up eth0" 0 "Bringing the connection up"
        rlRun "poll_cmd 15 'podman exec $dnsconfd_cid dig blocked.test.com | grep NXDOMAIN'" 0 "Waiting for RPZ zone transfer to complete"
        rlRun "podman exec $dnsconfd_cid getent hosts address.test.com | grep 192.168.6.10" 0 "Verifying non-blocked address resolves"
        rlRun "podman exec $dnsconfd_cid getent hosts blocked.test.com | grep 192.168.6.10" 1 "Verifying RPZ-blocked address does not resolve"
        rlRun "podman exec $dnsconfd_cid dig blocked.test.com | grep NXDOMAIN" 0 "Verifying RPZ returns NXDOMAIN for blocked domain"
    rlPhaseEnd

    rlPhaseStartTest "RPZ via glob include"
        rlRun "podman cp ./dnsconfd_glob_include.conf $dnsconfd_cid:/etc/dnsconfd/dnsconfd.conf" 0 "Copying glob include config"
        rlRun "podman exec $dnsconfd_cid systemctl restart dnsconfd" 0 "Restarting dnsconfd"
        rlRun "podman exec $dnsconfd_cid nmcli connection up eth0" 0 "Bringing the connection up"
        rlRun "poll_cmd 15 'podman exec $dnsconfd_cid dig blocked.test.com | grep NXDOMAIN'" 0 "Waiting for RPZ zone transfer to complete"
        rlRun "podman exec $dnsconfd_cid getent hosts address.test.com | grep 192.168.6.10" 0 "Verifying non-blocked address resolves"
        rlRun "podman exec $dnsconfd_cid getent hosts blocked.test.com | grep 192.168.6.10" 1 "Verifying RPZ-blocked address does not resolve"
        rlRun "podman exec $dnsconfd_cid dig blocked.test.com | grep NXDOMAIN" 0 "Verifying RPZ returns NXDOMAIN for blocked domain"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "podman exec $dnsconfd_cid journalctl -u dnsconfd" 0 "Saving dnsconfd logs"
        rlRun "podman exec $dnsconfd_cid journalctl -u unbound" 0 "Saving unbound logs"
        rlRun "podman exec $dnsconfd_cid journalctl -u NetworkManager" 0 "Saving NM logs"
        rlRun "podman logs $bind_cid" 0 "Saving BIND logs"
        rlRun "podman exec $dnsconfd_cid ip route" 0 "Saving present routes"
        rlRun "podman stop -t 0 $dnsconfd_cid $bind_cid $dnsmasq_cid" 0 "Stopping containers"
        rlRun "podman container rm $dnsconfd_cid $bind_cid $dnsmasq_cid" 0 "Removing containers"
        rlRun "podman network rm dnsconfd_network" 0 "Removing networks"
    rlPhaseEnd
rlJournalEnd
