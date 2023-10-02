#!/bin/bash
# vim: dict+=/usr/share/beakerlib/dictionary.vim cpt=.,w,b,u,t,i,k
. /usr/share/beakerlib/beakerlib.sh || exit 1
DBUS_NAME=org.freedesktop.resolve1

rlJournalStart
    rlPhaseStartSetup
        rlRun "set -o pipefail"
    rlPhaseEnd

    rlPhaseStartTest
        rlServiceStart dnsconfd
        sleep 2
        rlRun "dnsconfd -s --dbus-name=$DBUS_NAME | grep unbound" 0 "Verifying status of dnsconfd"
        # we can not simply check for a AVC until chrony issue is fixed
        rlRun "ausearch -m avc --start recent | grep dnsconfd_t" 1 "Check no AVC occured"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlServiceRestore dnsconfd
    rlPhaseEnd
rlJournalEnd
