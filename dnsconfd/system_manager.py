class SystemManager:
    def __init__(self, resolv_conf_path):
        self._backup = None
        self._resolv_conf_path = resolv_conf_path
        self.resolvconf_altered = False

    def setResolvconf(self):
        with open(self._resolv_conf_path, "r") as orig_resolv:
            self._backup = orig_resolv.read()
        with open(self._resolv_conf_path, "w") as new_resolv:
            new_resolv.write("nameserver 127.0.0.53\n")
        self.resolvconf_altered = True

    def revertResolvconf(self):
        with open(self._resolv_conf_path, "w") as new_resolv:
            new_resolv.write(self._backup)
        self.resolvconf_altered = False
