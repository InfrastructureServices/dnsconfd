# Dnsconfd

Dnsconfd simplifies configuration of local dns caching services by
providing layer of abstraction between them and system networking manager.

It is intended to be configured automatically from Network Manager and
to provide nice frontend, similar to resolvectl. Only some its features
are planned however.

## How to start it?

If you have deployed systemd-resolved or other such service, first disable it.
- ``systemctl disable --now systemd-resolved``
- ``systemctl mask systemd-resolved``

- ``dnsconfd config install`` - modifies NetworkManager to explicitly dnsconfd dbus API,
and changes ownership of resolvconf so Dnsconfd does not need root privileges
- ``systemctl enable --now dnsconfd``

## Testing

You can verify your changes by executing:

```
$ tmt run
```

This executes all test plans currently present for the project.

## Distribution

Dnsconfd is distributed as an RPM package that can be build for testing
purposes by executing `$ ./tests/build_package.sh`

## Currently supported DNS caching services

 - [Unbound](https://nlnetlabs.nl/projects/unbound/about/)

## Known limitations

 - DNSSEC validation is turned off to prevent potential problems. On well
   working networks it should work correctly. It disables validation even when
   *dnsconfd.service* is not started.

## Plans for future

 - Support more cache backends, at least *BIND9* and *dnsmasq*.
 - Have special handling of captive portals. Take inspiration from dnssec-trigger.
 - Have a nice frontend ``dnsconfctl``, similar to ``resolvectl``. Present current
   configuration in it, have it even localized.
 - Support for chain of servers, such as dnsmasq+dnsdist to provide DoT uplink even
   for dnsmasq or BIND 9.16 and earlier, which do not support it natively.
 - Support configuration from alternative network configuration daemons, like
   *systemd-networkd* or *dhcpcd*.
