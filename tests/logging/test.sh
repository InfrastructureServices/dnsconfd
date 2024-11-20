#!/bin/bash
# vim: dict+=/usr/share/beakerlib/dictionary.vim cpt=.,w,b,u,t,i,k
. /usr/share/beakerlib/beakerlib.sh || exit 1
ORIG_DIR=$(pwd)

rlJournalStart
    rlPhaseStartSetup
        rlRun "tmp=\$(mktemp -d)" 0 "Create tmp directory"
        rlRun "cp rsyslog.conf $tmp"
        rlRun "pushd $tmp"
        rlRun "set -o pipefail"
        # dns=none is neccessary, because otherwise resolv.conf is created and
        # mounted by podman as read-only
        rlRun "dnsconfd_cid=\$(podman run -d --dns='none' dnsconfd_testing:latest)" 0 "Starting dnsconfd container"
    rlPhaseEnd

    rlPhaseStartTest
        rlRun "podman exec $dnsconfd_cid systemctl start network-online.target"
        rlRun "podman exec $dnsconfd_cid touch /var/run/dnsconfd/dnsconfd.log" 0 "Create log file"
        rlRun "podman exec $dnsconfd_cid chown dnsconfd /var/run/dnsconfd/dnsconfd.log" 0 "Set log file ownership"
        rlRun "podman exec $dnsconfd_cid /bin/bash -c 'printf \"file_log: /var/run/dnsconfd/dnsconfd.log\n\" >> /etc/dnsconfd.conf'" 0 "Enabling file logging"
        rlRun "podman exec $dnsconfd_cid systemctl restart dnsconfd"
        rlRun "podman exec $dnsconfd_cid systemctl start network-online.target"
        rlRun "podman exec $dnsconfd_cid cat /var/run/dnsconfd/dnsconfd.log | grep 'ContextState.RUNNING'" 0 "verify logs are indeed in file"
        rlRun "podman exec $dnsconfd_cid systemctl stop rsyslog"
        rlRun "podman exec $dnsconfd_cid /bin/bash -c 'echo \"\" > /var/log/messages'"
        # now we will test syslog logging
        rlRun "podman cp rsyslog.conf $dnsconfd_cid:/etc/rsyslog.conf"
        rlRun "podman exec $dnsconfd_cid systemctl start rsyslog"
        rlRun "podman exec $dnsconfd_cid /bin/bash -c 'printf \"syslog_log: unix:/dev/newlog\n\" >> /etc/dnsconfd.conf'" 0 "Enabling syslog logging"
        rlRun "podman exec $dnsconfd_cid systemctl restart dnsconfd"
        rlRun "podman exec $dnsconfd_cid systemctl start network-online.target"
        rlRun "podman exec $dnsconfd_cid cat /var/log/messages | grep 'ContextState.RUNNING'" 0 "verify logs are indeed in syslog"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "podman exec $dnsconfd_cid journalctl -u dnsconfd" 0 "Saving dnsconfd logs"
        rlRun "popd"
        rlRun "podman stop -t 0 $dnsconfd_cid" 0 "Stopping containers"
        rlRun "podman container rm $dnsconfd_cid" 0 "Removing containers"
        rlRun "rm -r $tmp" 0 "Remove tmp directory"
    rlPhaseEnd
rlJournalEnd
