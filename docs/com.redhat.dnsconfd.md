# com.redhat.dnsconfd

version: **1.5.1**

## com.redhat.dnsconfd.Manager

### Methods

- **Update**(IN aa{sv} **servers**, IN u **mode**, OUT b **all_ok**, OUT s **message**)

  Change forwarders configuration of the underlying caching service.
  
  Arguments are:
  - **servers**: array of dictionaries, each representing server that should
  be set as a forwarder. Allowed keys are:
    - address: string or bytes containing server's ip address. Only this entry is required.
    - port: optional, integer indicating port number that should be used. Defaulting to `53` or `853` when `dns+tls` is used as protocol.
    - protocol: optional, string either `dns+udp`, `dns+tcp` or `dns+tls`. Defaulting to `dns+udp`.
    - name: optional, server name indication. Used when `DoT` is used to verify, presence of a right certificate. Defaulting to None.
    - routing_domains: optional, list of strings with the domain name whose members will be resolved only by this or other servers with the same domain entry
    - search_domains: optional, list of strings with the domains that should be used for host-name lookup
    - interface: optional, string indicating if server can be used only through interface with this interface name.
    - dnssec: optional, boolean indicating whether this server supports dnssec or not. Defaulting to `False`.
    - networks: optional, list of strings representing networks whose reverse dns records must be resolved by this server
    - connection-uuid: optional, string uuid of the connection associated with server in NetworkManager
    - connection-name: optional, string name of the connection associated with server in NetworkManager
    - connection-object: optional, string path of the connection object associated with server in NetworkManager
    - priority: optional, integer indicating priority of this server, lower means higher priority
    - firewall_zone: optional, string indicating name of firewall zone that this server should be associated with
  - **mode**: Unsigned integer representing resolving mode Dnsconfd should work in.
    - 0 - Free, all available server can be used for resolving of all names
    - 1 - Global restrictive, only global servers (not bound to interface) can be used for resolving of all names. Bound servers can resolve only subdomains
    - 2 - Full restrictive, only global servers will be used for resolving

  Returns:
  - **all_ok** Boolean indicating whether update was successfully submitted.
  - **message** Additional info about operation.
- **Status**(IN b **json_formatted**, OUT s **status**)
  
  Get status of dnsconfd.
  
  Arguments are:
  - **json_formatted**: Boolean indicating whether the output should be JSON formatted.
  
  Returns:
  - **status**: string indicating status of dnsconfd.

- **Reload**(OUT b **all_ok**, OUT s **message**)
  Reapply configuration of underlying cache service.
  
  Returns:
  - **all_ok**: boolean indicating whether reload was successfully submitted
  - **message**: String with dnsconfd reply.
