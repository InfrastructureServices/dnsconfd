#!/bin/bash
if [ ! -f /run/dnsconfd/unbound_control ]; then
    exit 0
fi

ACTION=$(cat /run/dnsconfd/unbound_control)
case "$ACTION" in
    stop)
        systemctl stop unbound.service
        ;;
    restart)
        systemctl restart unbound.service
        ;;
esac
