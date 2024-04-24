#!/bin/bash
# vim: dict+=/usr/share/beakerlib/dictionary.vim cpt=.,w,b,u,t,i,k
. /usr/share/beakerlib/beakerlib.sh || exit 1
DBUS_NAME=org.freedesktop.resolve1

rlJournalStart
    rlPhaseStartSetup
        rlRun "set -o pipefail"
        rlRun "useradd dummy" 0 "Adding dummy user"
        rlFileBackup /etc/sysconfig/unbound /etc/sysconfig/dnsconfd
        rlRun "echo 'LOG_LEVEL=DEBUG' >> /etc/sysconfig/dnsconfd"
        rlRun "echo 'DISABLE_UNBOUND_ANCHOR=yes' >> /etc/sysconfig/unbound"
    rlPhaseEnd

    rlPhaseStartTest
        rlRun "dnsconfd config nm_enable" 0 "Setting up NetworkManager"
        rlRun "dnsconfd config take_resolvconf" 0 "Changing resolv.conf ownership"
        rlServiceStart dnsconfd
        sleep 3
        rlRun "sudo -u dummy dnsconfd --dbus-name=$DBUS_NAME status | grep unbound" 0 "Verifying status of dnsconfd as dummy user"
        # we can not simply check for a AVC until chrony issue is fixed
        rlRun "sudo -u dummy dbus-send --system --dest=org.freedesktop.resolve1 --print-reply\
         --type=method_call /org/freedesktop/resolve1 \
         org.freedesktop.resolve1.Manager.RevertLink int32:1" 1 "Verify that regular user is not permitted to change DNS setting"
        rlRun "ausearch -m avc --start recent | grep dnsconfd_t" 1 "Check no AVC occured"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlServiceRestore dnsconfd
        rlFileRestore
        rlRun "journalctl -u dnsconfd" 0 "Saving logs"
        rlRun "dnsconfd config return_resolvconf" 0 "Returning privileges"
        rlRun "userdel dummy" 0 "Removing dummy user"
    rlPhaseEnd
rlJournalEnd
