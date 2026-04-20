#!/bin/bash

# Retry a command up to $1 seconds, polling every second.
# Returns 0 on first success, 1 on timeout.
poll_cmd() {
    local timeout=$1
    shift
    local elapsed=0
    while [ $elapsed -lt $timeout ]; do
        if eval "$@" >/dev/null 2>&1; then
            return 0
        fi
        sleep 1
        elapsed=$((elapsed + 1))
    done
    return 1
}

jq_filter_customized() {
  jq -c -S ". | {service, mode, cache_config: (.cache_config | map_values(sort)), servers: .servers | sort_by(\"address\") | map({$1})}"
}

jq_filter_general() {
  jq_filter_customized 'address, protocol, port, interface, routing_domains, search_domains, networks, firewall_zone, dnssec, name'
}
