# Dnsconfd

Dnsconfd simplifies configuration of local dns caching services by
implementing DBus interface of systemd-resolved and translating its
use to dns service's configuration.

It is intended to be configured automatically from Network Manager and
to provide nice frontend, similar to resolvectl. Only some its features
are planned however.

## How to start it?

Current version uses systemd-resolved plugin from Network Manager. Therefore it cannot run
together with *systemd-resolved.service* at the same time.

- ``systemctl disable --now systemd-resolved``
- ``systemctl mask systemd-resolved`` - prevents conflict of dbus service names
- ``dnsconfd config nm_enable`` - modifies NetworkManager to explicitly use systemd-resolved dbus API
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

## Documentation

You can build documentation with `$ sphinx-build -M html docs _build`

## Currently supported DNS caching services

 - [Unbound](https://nlnetlabs.nl/projects/unbound/about/)

## Known limitations

 - Unfortunately, intergration with NetworkManager is now only possible
   when Dnsconfd is allowed to own
   [org.freedesktop.resolve1](https://www.freedesktop.org/software/systemd/man/latest/org.freedesktop.resolve1.html)
   DBus name, as NetworkManager does not support use of any another.

 - Dnsconfd has to run as a root user, because NetworkManager forces us
   to use one of currently known resolv.conf stub files locations and
   we can not access them without root permission.

 - DNSSEC validation is turned off to prevent potential problems. On well
   working networks it should work correctly. It disables validation even when
   *dnsconfd.service* is not started.

## Plans for future

 - Support more cache backends, at least *BIND9* and *dnsmasq*.
 - Have special handling of captive portals. Take inspiration from dnssec-trigger.
 - Have working DNS over TLS configured via NM.
 - Implement own NM dns plugin, allowing us to not conflict with systemd-resolved
 - Have a nice frontend ``dnsconfctl``, similar to ``resolvectl``. Present current
   configuration in it, have it even localized.
 - Support for chain of servers, such as dnsmasq+dnsdist to provide DoT uplink even
   for dnsmasq or BIND 9.16 and earlier, which do not support it natively.
 - Support configuration from alternative network configuration daemons, like
   *systemd-networkd* or *dhcpcd*.
