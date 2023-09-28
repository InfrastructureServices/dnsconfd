#!/bin/bash

set -e

/usr/sbin/dhcpd -f -cf /etc/dhcp/dhcpd.conf "$@"
