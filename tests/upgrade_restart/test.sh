#!/bin/bash
# vim: dict+=/usr/share/beakerlib/dictionary.vim cpt=.,w,b,u,t,i,k
. /usr/share/beakerlib/beakerlib.sh || exit 1

# Maximum acceptable time in seconds for a daemon-reload + try-restart cycle.
# A healthy restart completes in under 1 second; the pre-fix hang was 45s.
RESTART_TIMEOUT=10

rlJournalStart
    rlPhaseStartSetup
        rlRun "set -o pipefail"
        rlRun "dnsconfd config nm_enable" 0 "Installing dnsconfd"
        rlServiceStart dnsconfd
        rlRun "systemctl is-active dnsconfd" 0 "dnsconfd is running"
        rlRun "systemctl is-active dnsconfd-unbound-control.path" 0 "path unit is running"
    rlPhaseEnd

    rlPhaseStartTest "daemon-reload plus service restart completes quickly"
        for i in 1 2 3; do
            rlLog "Run $i: daemon-reload + try-restart dnsconfd.service"
            START_TIME=$(date +%s)
            rlRun "systemctl daemon-reload" 0 "daemon-reload"
            rlRun "systemctl try-restart dnsconfd.service" 0 "try-restart dnsconfd"
            END_TIME=$(date +%s)
            ELAPSED=$((END_TIME - START_TIME))
            rlLog "Restart completed in ${ELAPSED}s"
            rlAssertGreater "restart must finish within ${RESTART_TIMEOUT}s" $RESTART_TIMEOUT $ELAPSED
            rlRun "systemctl is-active dnsconfd" 0 "dnsconfd is active after restart $i"
        done
    rlPhaseEnd

    rlPhaseStartTest "path unit not marked for restart in postun scriptlet"
        rlRun "rpm -q --scripts dnsconfd-unbound > scriptlets.txt" 0 "Getting dnsconfd-unbound scriptlets"
        rlRun "grep -q 'mark-restart-system-units.*dnsconfd-unbound-control.path' scriptlets.txt" 1 \
            "path unit must NOT be marked for restart in postun"
        rlLog "postuninstall scriptlet content:"
        rlRun "cat scriptlets.txt"
    rlPhaseEnd

    rlPhaseStartTest "no coredump or timeout during restart"
        CUR_TIME=$(date +%T)
        rlRun "systemctl daemon-reload" 0 "daemon-reload"
        rlRun "systemctl try-restart dnsconfd.service" 0 "try-restart dnsconfd"
        sleep 2
        rlRun "journalctl -u dnsconfd --since $CUR_TIME | grep -i 'timed out'" 1 \
            "no timeout messages in journal"
        rlRun "journalctl -u dnsconfd --since $CUR_TIME | grep -i 'SIGABRT'" 1 \
            "no SIGABRT in journal"
        rlRun "systemctl is-active dnsconfd" 0 "dnsconfd is active"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "journalctl -u dnsconfd" 0 "Saving dnsconfd logs"
        rlRun "journalctl -u unbound" 0 "Saving unbound logs"
        rlRun "journalctl -u dnsconfd-unbound-control.path" 0 "Saving path unit logs"
        rlRun "journalctl -u dnsconfd-unbound-control.service" 0 "Saving control service logs"
        rlServiceRestore dnsconfd
        rlRun "dnsconfd config uninstall" 0 "Uninstalling dnsconfd privileges"
        rlRun "rm -f scriptlets.txt"
    rlPhaseEnd
rlJournalEnd
