# com.redhat.dnsconfd

## com.redhat.dnsconfd.Manager

### Methods

- **Update**(IN aa{sv} **servers**, OUT b **all_ok**, OUT s **message**)

  Change forwarders configuration of the underlying caching service.
  
  Arguments are:
  - **servers**: array of dictionaries, each representing server that should
  be set as a forwarder. Allowed keys are:
    - address: string or bytes containing server's ip address. Only this entry is required.
    - port: integer indicating port number that should be used. Defaulting to `53` or `853` when `DoT` is used as protocol.
    - protocol: string either `plain` or `DoT`. Defaulting to `plain`.
    - sni: server name indication. Used when `DoT` is used to verify, presence of a right certificate. Defaulting to None.
    - domains: list of tuples with 2 members. The first member is string with the domain name whose members will be resolved only by this or other servers with the same domain entry. the second member is boolean indicating whether the domain should be used for resolving of host names.
      If '.' is present in the list, this server can be used for any name when no more specific domain entry of different server is present. Defaulting to `[('.', False)]`.
    - interface: integer indicating if server can be used only through interface with this interface index.
    - dnssec: boolean indicating whether this server supports dnssec or not. Defaulting to `False`.

  Returns:
  - **all_ok** Boolean indicating whether update was successfully submitted.
  - **message** Additional info about operation.
- **Status**(IN b **json_formatted**, OUT s **status**)
  
  Get status of dnsconfd.
 
  Arguments are:
  - **json_formatted**: Boolean indicating whether the output should be JSON formatted.
  Returns:
  - **status**: string indicating status of dnsconfd.

- **Reload**(OUT s **message**)
  Reapply configuration of underlying cache service.
  Returns:
  - **message**: String with dnsconfd reply.
