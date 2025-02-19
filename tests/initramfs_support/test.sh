#!/bin/bash
# vim: dict+=/usr/share/beakerlib/dictionary.vim cpt=.,w,b,u,t,i,k
. /usr/share/beakerlib/beakerlib.sh || exit 1
. "$TMT_TOPOLOGY_BASH"

rlJournalStart
    rlPhaseStartSetup
        rlRun "set -o pipefail"
    rlPhaseEnd

    rlPhaseStartTest
        if [ "${TMT_GUEST[name]}" = "client" ]; then
            if [ "$TMT_REBOOT_COUNT" -eq 0 ]; then
              rlRun "nc -l 8888"
              rlRun "mkdir -p /etc/pki/dns/extracted/pem/"
              rlRun "cp ca_cert.pem /etc/pki/dns/extracted/pem/tls-ca-bundle.pem"
              rlRun "mkdir -p /lib/dracut/modules.d/99test-resolve"
              rlRun "cp ./module-setup.sh /lib/dracut/modules.d/99test-resolve"
              rlRun "cp ./test-resolve.service /lib/dracut/modules.d/99test-resolve"
              rlRun "cp ./test-resolve.service /usr/lib/systemd/system/test-resolve.service"
              rlRun "sed -i 's/\(GRUB_CMDLINE_LINUX.*=\".*\)\"/\1 rd.neednet rd.net.dns=dns+tls:\/\/${TMT_GUESTS[server.hostname]}#named ip=dhcp\"/g' /etc/default/grub"
              rlRun "grubby --update-kernel=/boot/vmlinuz-$(uname -r) --args=\"rd.neednet rd.net.dns=dns+tls://${TMT_GUESTS[server.hostname]}#named ip=dhcp rd.net.dns-global-mode=exclusive rd.net.dns-backend=dnsconfd\""
              rlRun "dracut --force" 0 "Rebuild initramfs"
              rlRun "grub2-mkconfig -o /boot/grub2/grub.cfg"
              rlRun "tmt-reboot" 0 "Reboot the machine"
            else
              rlRun "journalctl -u test-resolve | grep 192.168.6.5"
              rlRun "journalctl -u test-resolve"
              rlRun "journalctl -u micro-dnsconfd"
              rlRun "journalctl -u unbound"
              rlRun "journalctl -u NetworkManager"
              rlRun "while ! echo 'finish' | nc ${TMT_GUESTS[server.hostname]} 8888; do sleep 2; done"
            fi
        else
          rlRun "while ! echo 'start' | nc ${TMT_GUESTS[client.hostname]} 8888; do sleep 2; done"
          rlRun "journalctl -u named"
          rlRun "nc -l 8888"
        fi
    rlPhaseEnd

    rlPhaseStartCleanup

    rlPhaseEnd
rlJournalEnd
