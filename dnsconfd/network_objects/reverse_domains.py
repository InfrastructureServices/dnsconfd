#!/usr/bin/python
#
# Implement and test generation of IP ranges from network

import ipaddress

def reverse_zones4(net: ipaddress._BaseNetwork):
    # inspired by ipaddress._BaseV4._reverse_pointer
    bitsperlabel=8
    domains = []
    host_bits = net.max_prefixlen - net.prefixlen
    strip_labels = int(host_bits / bitsperlabel)
    remain_bits = host_bits % bitsperlabel
    for n in net.subnets(remain_bits):
        s = str(n)
        reversed_octets = s[0:s.rindex('/')].split('.')[::-1]
        reversed_octets.append('in-addr.arpa')
        domain = '.'.join(reversed_octets[strip_labels:])
        domains.append(domain)
    return domains

def reverse_zones6(net: ipaddress._BaseNetwork):
    # inspired by ipaddress._BaseV6._reverse_pointer
    bitsperlabel=4
    domains = []
    host_bits = net.max_prefixlen - net.prefixlen
    strip_labels = int(host_bits / bitsperlabel)
    remain_bits = host_bits % bitsperlabel
    for n in net.subnets(remain_bits):
        s = n.exploded[::-1]
        reverse_chars = s[s.index('/')+1:].replace(':', '') # just ip reversed, without :
        labels = reverse_chars[strip_labels:]
        domain = '.'.join(labels)
        if domain:
            domain += '.'
        domain += 'ip6.arpa'
        domains.append(domain)
    return domains

def reverse_zones(net: ipaddress._BaseNetwork):
    if net.version == 4:
        return reverse_zones4(net)
    elif net.version == 6:
        return reverse_zones6(net)
    else:
        raise ValueError("Unsupported IP version")

__all__ = [ reverse_zones4, reverse_zones6, reverse_zones ]
