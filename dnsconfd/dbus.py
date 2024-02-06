"""DBus constants module."""

# Our future dbus service name. Not yet used.
DNSCONFD_NAME = 'com.redhat.dnsconfd'

# Implements systemd-resolved interfaces defined at:
# https://www.freedesktop.org/software/systemd/man/latest/org.freedesktop.resolve1.html
# or man 5 org.freedesktop.resolve1
RESOLVED_NAME = 'org.freedesktop.resolve1'
RESOLVED_MANAGER_IFACE = RESOLVED_NAME+'.Manager'
RESOLVED_DNSCONFD_IFACE = RESOLVED_NAME+'.Dnsconfd'
RESOLVED_PATH = "/org/freedesktop/resolve1"

# https://networkmanager.dev/docs/api/latest/spec.html
NM_NAME = "org.freedesktop.NetworkManager"
NM_PATH = "/org/freedesktop/NetworkManager"
NM_IFACE = NM_NAME
NM_DNS_PATH = "/org/freedesktop/NetworkManager/DnsManager"
NM_DNS_IFACE = "org.freedesktop.NetworkManager.DnsManager"
NM_DEVICE_IFACE = "org.freedesktop.NetworkManager.Device"
NM_IP4CONFIG_IFACE = "org.freedesktop.NetworkManager.IP4Config"
NM_IP6CONFIG_IFACE = "org.freedesktop.NetworkManager.IP6Config"
__all__ = [ DNSCONFD_NAME,
            RESOLVED_NAME, RESOLVED_MANAGER_IFACE, RESOLVED_DNSCONFD_IFACE,
            RESOLVED_PATH,
            NM_NAME, NM_PATH, NM_IFACE, NM_DNS_PATH, NM_DNS_IFACE, NM_DEVICE_IFACE,
            NM_IP4CONFIG_IFACE, NM_IP6CONFIG_IFACE ]
