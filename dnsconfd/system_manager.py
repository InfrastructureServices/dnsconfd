import logging as lgr

class SystemManager:
    def __init__(self, resolv_conf_path):
        self._backup = None
        self._resolv_conf_path = resolv_conf_path
        self.resolvconf_altered = False

    def setResolvconf(self):
        with open(self._resolv_conf_path, "r") as orig_resolv:
            self._backup = orig_resolv.read()
        with open(self._resolv_conf_path, "w") as new_resolv:
            new_resolv.write(self._getResolvconfString())
        self.resolvconf_altered = True

    def _getResolvconfString(self, search_domains = []):
        conf = "nameserver 127.0.0.1\n"
        if len(search_domains):
            conf += f"search {' '.join(search_domains)}\n"
        return conf

    def revertResolvconf(self):
        with open(self._resolv_conf_path, "w") as new_resolv:
            new_resolv.write(self._backup)
        self.resolvconf_altered = False

    def updateResolvconf(self, search_domains):
        lgr.debug(f"Updating resolvconf with domains {search_domains}")
        with open(self._resolv_conf_path, "w") as new_resolv:
            new_resolv.write(self._getResolvconfString(search_domains))
