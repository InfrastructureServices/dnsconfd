#!/bin/bash
# vim: dict+=/usr/share/beakerlib/dictionary.vim cpt=.,w,b,u,t,i,k
. /usr/share/beakerlib/beakerlib.sh || exit 1
DBUS_NAME=org.freedesktop.resolve1

rlJournalStart
    rlPhaseStartSetup
        rlRun "tmp=\$(mktemp -d)" 0 "Create tmp directory"
        rlRun "cp ./rsyslog.conf $tmp/"
        rlFileBackup /etc/rsyslog.conf
        rlRun "pushd $tmp"
        rlRun "set -o pipefail"
    rlPhaseEnd

    rlPhaseStartTest
        rlRun "dnsconfd config nm_enable" 0 "Installing dnsconfd"
        rlServiceStop rsyslog
        rlRun "echo '' > /var/log/messages"
        # now we will test syslog logging
        rlRun "cp rsyslog.conf /etc/rsyslog.conf"
        rlServiceStart rsyslog
        rlRun "printf 'syslog_log: unix:/dev/newlog\n' >> /etc/dnsconfd.conf" 0 "Enabling syslog logging"
        rlServiceStart dnsconfd
        sleep 3
        rlRun "cat /var/log/messages | grep 'ContextState.RUNNING'" 0 "verify logs are indeed in syslog"
        rlServiceStop rsyslog
        rlRun "echo '' > /var/log/messages"
        rlRun "printf 'syslog_log: udp:127.0.0.1:514\n' >> /etc/dnsconfd.conf" 0 "Enabling syslog logging with udp"
        rlServiceStart rsyslog
        rlServiceStart dnsconfd
        sleep 3
        rlRun "cat /var/log/messages | grep 'ContextState.RUNNING'" 0 "verify logs are indeed in syslog"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "journalctl -u dnsconfd" 0 "Saving dnsconfd logs"
        rlRun "journalctl -u unbound" 0 "Saving unbound logs"
        rlRun "ip route" 0 "Saving present routes"
        rlServiceRestore dnsconfd
        rlServiceRestore rsyslog
        rlFileRestore
        rlRun "journalctl -u dnsconfd" 0 "Saving logs"
        rlRun "dnsconfd config uninstall" 0 "Uninstalling dnsconfd privileges"
    rlPhaseEnd
rlJournalEnd
