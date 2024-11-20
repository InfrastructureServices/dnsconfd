#!/bin/bash

if [ "$(stat --format %U /etc/resolv.conf)" == "dnsconfd" ]; then
  dnsconfd config return_resolvconf
fi
# on systems where local root caching was default and we can not
# change distribution default, attempt to enable the feature
# manually
if [ -f /etc/unbound/conf.d/unbound-local-root.conf.disabled  ]; then
    mv -f /etc/unbound/conf.d/unbound-local-root.conf.disabled /etc/unbound/conf.d/unbound-local-root.conf
fi
# revert our disabling of unbound-anchor
rm -f /run/unbound/anchor-disable
# revert enablement of as112 domain resolution
if [ -e /etc/unbound/conf.d/dnsconfd-as112.conf ]; then
  rm -f /etc/unbound/conf.d/dnsconfd-as112.conf
fi
