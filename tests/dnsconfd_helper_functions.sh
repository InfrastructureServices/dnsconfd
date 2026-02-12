#!/bin/bash

jq_filter_customized() {
  jq -c -S ". | {service, mode, cache_config: (.cache_config | map_values(sort)), servers: .servers | sort_by(\"address\") | map({$1})}"
}

jq_filter_general() {
  jq_filter_customized 'address, protocol, port, interface, routing_domains, search_domains, networks, firewall_zone, dnssec, name'
}
