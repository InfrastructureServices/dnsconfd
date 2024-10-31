#!/bin/bash

jq_filter_customized() {
  jq -c -S ". | {service, cache_config, servers: .servers | sort_by(\"address\") | map({$1})}"
}

jq_filter_general() {
  jq_filter_customized 'address, protocol, port, interface, routing_domains, search_domains, networks, firewall_zone, dnssec, name'
}
