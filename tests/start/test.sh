#!/bin/bash
# vim: dict+=/usr/share/beakerlib/dictionary.vim cpt=.,w,b,u,t,i,k
. /usr/share/beakerlib/beakerlib.sh || exit 1
DBUS_NAME=org.freedesktop.resolve1

rlJournalStart
    rlPhaseStartSetup
        rlRun "set -o pipefail"
        rlFileBackup /etc/sysconfig/dnsconfd
        rlRun "echo 'LOG_LEVEL=DEBUG' >> /etc/sysconfig/dnsconfd"
    rlPhaseEnd

    rlPhaseStartTest
        rlRun "dnsconfd config install" 0 "Installing dnsconfd"
        rlServiceStart dnsconfd
        sleep 2
        rlRun "dnsconfd --dbus-name=$DBUS_NAME status | grep unbound" 0 "Verifying status of dnsconfd"
        # we can not simply check for a AVC until chrony issue is fixed
        rlRun "ausearch -m avc --start recent | grep dnsconfd" 1 "Check no AVC occured"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlServiceRestore dnsconfd
        rlFileRestore
        rlRun "journalctl -u dnsconfd" 0 "Saving logs"
        rlRun "dnsconfd config uninstall" 0 "Uninstalling dnsconfd privileges"
    rlPhaseEnd
rlJournalEnd
