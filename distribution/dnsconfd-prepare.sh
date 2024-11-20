#!/bin/bash

if [ "$(stat --format %U /etc/resolv.conf)" != "dnsconfd" ]; then
  dnsconfd config take_resolvconf
fi
# on systems where local root caching was default and we can not
# change distribution default, attempt to disable the feature
# manually
if [ -f /etc/unbound/conf.d/unbound-local-root.conf ]; then
    mv -f /etc/unbound/conf.d/unbound-local-root.conf /etc/unbound/conf.d/unbound-local-root.conf.disabled
fi
# unbound-anchor checks for this file and will not start if it is present
touch /run/unbound/anchor-disable
# revert enablement of as112 domain resolution
if ! [ -e /etc/unbound/conf.d/dnsconfd-as112.conf ]; then
  ln -s /usr/share/unbound/conf.d/unbound-as112-networks.conf /etc/unbound/conf.d/dnsconfd-as112.conf
fi
