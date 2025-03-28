#!/bin/bash
# vim: dict+=/usr/share/beakerlib/dictionary.vim cpt=.,w,b,u,t,i,k
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "set -o pipefail"
        rlRun "useradd dummy" 0 "Adding dummy user"
    rlPhaseEnd

    rlPhaseStartTest
        rlRun "dnsconfd config nm_enable" 0 "Installing dnsconfd"
        rlServiceStart dnsconfd
        rlRun "sudo -u dummy dnsconfd status | grep unbound" 0 "Verifying status of dnsconfd as dummy user"
        # we can not simply check for a AVC until chrony issue is fixed
        rlRun "sudo -u dummy dbus-send --system --dest=org.freedesktop.resolve1 --print-reply\
         --type=method_call /org/freedesktop/resolve1 \
         org.freedesktop.resolve1.Manager.RevertLink int32:1" 1 "Verify that regular user is not permitted to change DNS setting"
        rlRun "ausearch -m avc --start recent | grep dnsconfd" 1 "Check no AVC occured"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "journalctl -u dnsconfd" 0 "Saving dnsconfd logs"
        rlRun "journalctl -u unbound" 0 "Saving unbound logs"
        rlRun "ip route" 0 "Saving present routes"
        rlServiceRestore dnsconfd
        rlFileRestore
        rlRun "journalctl -u dnsconfd" 0 "Saving logs"
        rlRun "dnsconfd config uninstall" 0 "Uninstalling dnsconfd privileges"
        rlRun "userdel dummy" 0 "Removing dummy user"
    rlPhaseEnd
rlJournalEnd
