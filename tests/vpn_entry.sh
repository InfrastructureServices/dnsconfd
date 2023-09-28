#!/bin/bash

set -e

/usr/sbin/openvpn --status-version 2 --suppress-timestamps --cipher AES-256-GCM --data-ciphers AES-256-GCM:AES-128-GCM:AES-256-CBC:AES-128-CBC --config /etc/openvpn/serverudp.conf "$@"
