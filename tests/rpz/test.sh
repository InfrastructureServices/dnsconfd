#!/bin/bash
# vim: dict+=/usr/share/beakerlib/dictionary.vim cpt=.,w,b,u,t,i,k
. /usr/share/beakerlib/beakerlib.sh || exit 1
. ../dnsconfd_helper_functions.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "podman network create dnsconfd_network --internal -d=bridge --gateway=192.168.6.1 --subnet=192.168.6.0/24"
        # dns=none is necessary, because otherwise resolv.conf is created and
        # mounted by podman as read-only
        rlRun "dnsconfd_cid=\$(podman run --privileged -d --dns='none' --network dnsconfd_network:ip=192.168.6.2 dnsconfd_testing:latest)" 0 "Starting dnsconfd container"
        rlRun "bind_cid=\$(podman run -d --dns='none' --network dnsconfd_network:ip=192.168.6.3 localhost/dnsconfd_utilities:latest /usr/sbin/named -u named -g -d 5 -c /etc/named.conf)" 0 "Starting BIND container with RPZ zone"
        rlRun "dnsmasq_cid=\$(podman run -d --dns='none' --network dnsconfd_network:ip=192.168.6.10 localhost/dnsconfd_utilities:latest\
               dnsmasq_entry.sh --listen-address=192.168.6.10 --address=/address.test.com/192.168.6.10 --address=/blocked.test.com/192.168.6.10)" 0 "Starting dnsmasq container"
    rlPhaseEnd

    rlPhaseStartTest "RPZ with master only"
        rlRun "podman cp ./dnsconfd.conf $dnsconfd_cid://etc/dnsconfd.conf" 0 "Copying RPZ config into container"
        rlRun "podman exec $dnsconfd_cid systemctl restart dnsconfd" 0 "Restarting dnsconfd with RPZ config"
        rlRun "podman exec $dnsconfd_cid nmcli connection mod eth0 ipv4.dns 192.168.6.10" 0 "Adding dns server to NM active profile"
        rlRun "podman exec $dnsconfd_cid nmcli connection up eth0" 0 "Bringing the connection up"
        rlRun "poll_cmd 15 'podman exec $dnsconfd_cid dig blocked.test.com | grep NXDOMAIN'" 0 "Waiting for RPZ zone transfer to complete"
        rlRun "podman exec $dnsconfd_cid getent hosts address.test.com | grep 192.168.6.10" 0 "Verifying non-blocked address resolves"
        rlRun "podman exec $dnsconfd_cid getent hosts blocked.test.com | grep 192.168.6.10" 1 "Verifying RPZ-blocked address does not resolve"
        rlRun "podman exec $dnsconfd_cid dig blocked.test.com | grep NXDOMAIN" 0 "Verifying RPZ returns NXDOMAIN for blocked domain"
        # dynamically add address.test.com to the RPZ block list on BIND
        rlRun "podman exec $bind_cid /bin/bash -c 'printf \"server 127.0.0.1\nzone rpz.dnsconfd.test\nupdate add address.test.com.rpz.dnsconfd.test. 86400 CNAME .\nsend\n\" | nsupdate'" 0 "Adding address.test.com to RPZ zone via nsupdate"
        rlRun "poll_cmd 15 'podman exec $dnsconfd_cid dig address.test.com | grep NXDOMAIN'" 0 "Waiting for RPZ update to propagate"
        rlRun "podman exec $dnsconfd_cid dig address.test.com | grep NXDOMAIN" 0 "Verifying RPZ update propagated and blocks address.test.com"
    rlPhaseEnd

    rlPhaseStartTest "RPZ with zonefile only"
        # remove address.test.com from BIND RPZ so it won't interfere if
        # unbound somehow still contacts the master
        rlRun "podman exec $bind_cid /bin/bash -c 'printf \"server 127.0.0.1\nzone rpz.dnsconfd.test\nupdate delete address.test.com.rpz.dnsconfd.test. CNAME\nsend\n\" | nsupdate'" 0 "Removing address.test.com from BIND RPZ zone"
        rlRun "podman exec $dnsconfd_cid cp /dev/null /var/lib/unbound/rpz.dnsconfd.test" 0 "Ensuring clean zonefile path"
        rlRun "podman cp ../bind_zones/rpz.dnsconfd.test $dnsconfd_cid:/var/lib/unbound/rpz.dnsconfd.test" 0 "Copying RPZ zone file into container"
        rlRun "podman exec $dnsconfd_cid chown unbound:unbound /var/lib/unbound/rpz.dnsconfd.test" 0 "Setting zone file ownership"
        rlRun "podman cp ./dnsconfd_zonefile.conf $dnsconfd_cid://etc/dnsconfd.conf" 0 "Copying zonefile-only RPZ config into container"
        rlRun "podman exec $dnsconfd_cid systemctl restart dnsconfd" 0 "Restarting dnsconfd with zonefile-only RPZ config"
        rlRun "podman exec $dnsconfd_cid nmcli connection up eth0" 0 "Bringing the connection up"
        rlRun "poll_cmd 15 'podman exec $dnsconfd_cid dig blocked.test.com | grep NXDOMAIN'" 0 "Waiting for RPZ zonefile to become active"
        rlRun "podman exec $dnsconfd_cid getent hosts address.test.com | grep 192.168.6.10" 0 "Verifying non-blocked address resolves with zonefile-only config"
        rlRun "podman exec $dnsconfd_cid getent hosts blocked.test.com | grep 192.168.6.10" 1 "Verifying RPZ-blocked address does not resolve with zonefile-only config"
        rlRun "podman exec $dnsconfd_cid dig blocked.test.com | grep NXDOMAIN" 0 "Verifying RPZ returns NXDOMAIN for blocked domain with zonefile-only config"
    rlPhaseEnd

    rlPhaseStartTest "RPZ with both master and zonefile"
        rlRun "podman cp ./dnsconfd_both.conf $dnsconfd_cid://etc/dnsconfd.conf" 0 "Copying master+zonefile RPZ config into container"
        rlRun "podman exec $dnsconfd_cid systemctl restart dnsconfd" 0 "Restarting dnsconfd with master+zonefile RPZ config"
        rlRun "podman exec $dnsconfd_cid nmcli connection up eth0" 0 "Bringing the connection up"
        rlRun "poll_cmd 15 'podman exec $dnsconfd_cid dig blocked.test.com | grep NXDOMAIN'" 0 "Waiting for RPZ zone to become active"
        rlRun "podman exec $dnsconfd_cid getent hosts address.test.com | grep 192.168.6.10" 0 "Verifying non-blocked address resolves with master+zonefile config"
        rlRun "podman exec $dnsconfd_cid getent hosts blocked.test.com | grep 192.168.6.10" 1 "Verifying RPZ-blocked address does not resolve with master+zonefile config"
        rlRun "podman exec $dnsconfd_cid dig blocked.test.com | grep NXDOMAIN" 0 "Verifying RPZ returns NXDOMAIN for blocked domain with master+zonefile config"
        # dynamically add address.test.com to the RPZ block list on BIND
        rlRun "podman exec $bind_cid /bin/bash -c 'printf \"server 127.0.0.1\nzone rpz.dnsconfd.test\nupdate add address.test.com.rpz.dnsconfd.test. 86400 CNAME .\nsend\n\" | nsupdate'" 0 "Adding address.test.com to RPZ zone via nsupdate"
        rlRun "poll_cmd 15 'podman exec $dnsconfd_cid dig address.test.com | grep NXDOMAIN'" 0 "Waiting for RPZ update to propagate"
        rlRun "podman exec $dnsconfd_cid dig address.test.com | grep NXDOMAIN" 0 "Verifying RPZ update propagated with master+zonefile config"
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
