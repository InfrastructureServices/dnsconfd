# Dnsconfd

Dnsconfd simplifies configuration of local dns caching services by
implementing DBus interface of systemd-resolved and translating its
use to dns service's configuration.

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

- Unbound

## Known limitations

 - Unfortunately, intergration with NetworkManager is now only possible
   when Dnsconfd is allowed to own org.freedesktop.resolve1 DBus name,
   as NetworkManager does not support use of any another.

 - Dnsconfd has to run as a root user, because NetworkManager forces us
   to use one of currently known resolv.conf stub files locations and
   we can not access them without root permission.
