#!/bin/bash
# vim: dict+=/usr/share/beakerlib/dictionary.vim cpt=.,w,b,u,t,i,k
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "tmp=\$(mktemp -d)" 0 "Create tmp directory"
        rlRun "pushd $tmp"
        rlRun "set -o pipefail"
        rlFileBackup /etc/sysconfig/dnsconfd
    rlPhaseEnd

    rlPhaseStartTest
        rlRun "dnsconfd config nm_enable" 0 "Installing dnsconfd"
        CUR_TIME=$(date +%T)
        rlRun "printf \"SYSLOG_LOG: yes\nSTDERR_LOG: no\n\" >> /etc/sysconfig/dnsconfd" 0 "Enabling syslog logging"
        rlServiceStart dnsconfd
        sleep 3
        rlRun "journalctl --since \"$CUR_TIME\" | grep 'RUNNING'" 0 "verify logs are indeed in syslog"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "journalctl -u dnsconfd" 0 "Saving dnsconfd logs"
        rlRun "journalctl -u unbound" 0 "Saving unbound logs"
        rlRun "ip route" 0 "Saving present routes"
        rlServiceRestore dnsconfd
        rlFileRestore
        rlRun "journalctl -u dnsconfd" 0 "Saving logs"
        rlRun "dnsconfd config uninstall" 0 "Uninstalling dnsconfd privileges"
    rlPhaseEnd
rlJournalEnd
