class SystemManager:
    def __init__(self):
        self.backup = None
        self.resolvconf_altered = False

    def setResolvconf(self):
        with open("/usr/lib/systemd/resolv.conf", "r") as orig_resolv:
            self.backup = orig_resolv.read()
        with open("/usr/lib/systemd/resolv.conf", "w") as new_resolv:
            new_resolv.write("nameserver 127.0.0.53\n")
        self.resolvconf_altered = True

    def revertResolvconf(self):
        with open("/usr/lib/systemd/resolv.conf", "w") as new_resolv:
            new_resolv.write(self.backup)
        self.resolvconf_altered = False
