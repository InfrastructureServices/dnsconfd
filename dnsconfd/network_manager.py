import subprocess


class NetworkManager:
    NM_CONF_D = "/etc/NetworkManager/conf.d"
    NM_CONF = NM_CONF_D + "/dnsconfd.conf"
    HEADER = "## This file is maintained by " \
             "dnsconfd tool, do not edit by hand!\n"

    @staticmethod
    def reload():
        """ Perform reload of Network Manager """
        subprocess.run(["systemctl", "reload", "NetworkManager"],
                       capture_output=True,
                       check=True)

    def enable(self) -> bool:
        """ Enables dnsconfd in Network Manager. Requires root privileges. """
        try:
            with open(self.NM_CONF, "w", encoding="utf-8") as f:
                # TODO: have own plugin in NM
                f.writelines([self.HEADER,
                              "[main]\n",
                              "dns=dnsconfd\n"])
        except OSError as e:
            print(f"Unable to configure network manager: {e}")
            return False
        self.reload()
        return True

    def disable(self) -> bool:
        """ Disables dnsconfd in Network Manager. Requires root privileges. """
        try:
            with open(self.NM_CONF, "w", encoding="utf-8") as f:
                f.writelines([self.HEADER])
        except OSError as e:
            print(f"Unable to configure network manager: {e}")
            return False
        self.reload()
        return True
