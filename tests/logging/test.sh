#!/bin/bash
# vim: dict+=/usr/share/beakerlib/dictionary.vim cpt=.,w,b,u,t,i,k
. /usr/share/beakerlib/beakerlib.sh || exit 1
ORIG_DIR=$(pwd)

rlJournalStart
    rlPhaseStartSetup
        rlRun "tmp=\$(mktemp -d)" 0 "Create tmp directory"
        rlRun "pushd $tmp"
        rlRun "set -o pipefail"
        # dns=none is neccessary, because otherwise resolv.conf is created and
        # mounted by podman as read-only
        rlRun "dnsconfd_cid=\$(podman run --privileged -d --dns='none' dnsconfd_testing:latest)" 0 "Starting dnsconfd container"
        # give systemd in container time to open the dbus socket
        until podman exec $dnsconfd_cid systemctl is-system-running --quiet 2>/dev/null; do
            sleep 0.1
        done
    rlPhaseEnd

    rlPhaseStartTest
        rlRun "podman exec $dnsconfd_cid systemctl start network-online.target"
        rlRun "podman exec $dnsconfd_cid touch /var/run/dnsconfd/dnsconfd.log" 0 "Create log file"
        rlRun "podman exec $dnsconfd_cid chown dnsconfd /var/run/dnsconfd/dnsconfd.log" 0 "Set log file ownership"
        rlRun "podman exec $dnsconfd_cid /bin/bash -c 'printf \"file_log: /var/run/dnsconfd/dnsconfd.log\n\" >> /etc/dnsconfd.conf'" 0 "Enabling file logging"
        rlRun "podman exec $dnsconfd_cid systemctl restart dnsconfd"
        rlRun "podman exec $dnsconfd_cid systemctl start network-online.target"
        rlRun "podman exec $dnsconfd_cid cat /var/run/dnsconfd/dnsconfd.log | grep 'RUNNING'" 0 "verify logs are indeed in file"
        # syslog logging now
        CUR_TIME=$(date +%T)
        rlRun "podman exec $dnsconfd_cid /bin/bash -c 'printf \"SYSLOG_LOG: yes\nSTDERR_LOG: no\n\" >> /etc/sysconfig/dnsconfd'" 0 "Enabling syslog logging"
        rlRun "podman exec $dnsconfd_cid systemctl restart dnsconfd"
        sleep 3
        rlRun "podman exec $dnsconfd_cid journalctl --since \"$CUR_TIME\" | grep 'RUNNING'" 0 "verify logs are indeed in syslog"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "podman exec $dnsconfd_cid journalctl -u dnsconfd" 0 "Saving dnsconfd logs"
        rlRun "popd"
        rlRun "podman stop -t 0 $dnsconfd_cid" 0 "Stopping containers"
        rlRun "podman container rm $dnsconfd_cid" 0 "Removing containers"
        rlRun "rm -r $tmp" 0 "Remove tmp directory"
    rlPhaseEnd
rlJournalEnd
