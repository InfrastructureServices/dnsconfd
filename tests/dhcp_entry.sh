#!/bin/bash

set -e

/usr/sbin/dhcpd -f -cf "$@"
