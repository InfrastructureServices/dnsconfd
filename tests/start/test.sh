#!/bin/bash
# vim: dict+=/usr/share/beakerlib/dictionary.vim cpt=.,w,b,u,t,i,k
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "set -o pipefail"
        rlFileBackup /etc/dnsconfd.conf
    rlPhaseEnd

    rlPhaseStartTest
        rlRun "dnsconfd config nm_enable" 0 "Installing dnsconfd"
        rlServiceStart dnsconfd
        sleep 2
        rlRun "dnsconfd status | grep unbound" 0 "Verifying status of dnsconfd"
        # test also new api
        rlRun "echo 'api_choice: dnsconfd' >> /etc/dnsconfd.conf"
        rlServiceStart dnsconfd
        rlRun "dnsconfd update --json '[{\"address\":\"192.168.6.3\", \"interface\": \"eth0\"}]'"
        sleep 2
        rlRun "dnsconfd status | grep unbound" 0 "Verifying status of dnsconfd"
        # we can not simply check for a AVC until chrony issue is fixed
        rlRun "ausearch -m avc --start recent | grep dnsconfd" 1 "Check no AVC occured"
        rlRun "ls -Z /bin/dnsconfd | grep dnsconfd_exec_t" 0 "Verify that dnsconfd executable has right context"
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
