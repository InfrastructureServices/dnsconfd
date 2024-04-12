import subprocess


class NetworkManager(object):
    NM_CONF_D = "/etc/NetworkManager/conf.d"
    NM_CONF = NM_CONF_D + "/dnsconf.conf"
    HEADER = "## This file is maintained by "\
             "dnsconfd tool, do not edit by hand!\n"

    @staticmethod
    def reload():
        """ Perform reload of Network Manager """
        cmd = subprocess.run(["systemctl", "reload", "NetworkManager"],
                             capture_output=True,
                             check=True)
        print(cmd.stdout)

    def enable(self):
        """ Enables dnsconfd in Network Manager. Requires root privileges. """
        with open(self.NM_CONF, "w") as f:
            # TODO: have own plugin in NM
            f.writelines([self.HEADER,
                          "[main]\n",
                          "dns=systemd-resolved\n",
                          "rc-manager=unmanaged\n"])
        self.reload()

    def disable(self):
        """ Disables dnsconfd in Network Manager. Requires root privileges. """
        with open(self.NM_CONF, "w") as f:
            f.writelines([self.HEADER])
        self.reload()
