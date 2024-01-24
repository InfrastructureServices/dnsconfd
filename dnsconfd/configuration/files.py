#!/usr/bin/python3

import os
import configparser

class Files(configparser.ConfigParser):
    """Wrapping class reading configuration from multiple files."""

    SYSCONFDIR = "/etc/dnsconfd"
    DEFAULT_PATH = SYSCONFDIR + "/dnsconfd.conf"
    DEFAULT_CONFDIR = SYSCONFDIR + "/conf.d"
    DEFAULT_SECTION = 'main'
    CONF_SUFFIX = '.conf'
    DEFAULTS = { 'config_directory': DEFAULT_CONFDIR, }

    def __init__(self, *args, **kwargs):
        super(configparser.ConfigParser, self).__init__(*args, **kwargs,
                                                        defaults=self.DEFAULTS,
                                                        default_section=self.DEFAULT_SECTION)

    def read_default(self):
        files = self.read([self.DEFAULT_PATH])
        confd = self.get(self.DEFAULT_SECTION, 'config_directory')
        if confd and os.path.isdir(confd):
            dirfiles = []
            for fpath in os.scandir(confd):
                if fpath.is_file() and os.path.splitext(fpath)[1] == self.CONF_SUFFIX:
                    dirfiles.append(fpath)
            files.extend(self._read_dirfile(dirfiles))
            return files

    def _read_dirfile(self, paths):
        return self.read(paths)

    def getdef(self, option):
        return self.get(self.DEFAULT_SECTION, option)
