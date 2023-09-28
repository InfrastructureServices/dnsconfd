#!/bin/bash

set -e

/usr/sbin/dnsmasq -d --no-resolv --no-hosts "$@"
