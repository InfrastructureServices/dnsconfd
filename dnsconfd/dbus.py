"""DBus constants module."""

# Our future dbus service name. Not yet used.
DEST_DNSCONFD = 'com.redhat.dnsconfd'

# Implements systemd-resolved interfaces defined at:
# https://www.freedesktop.org/software/systemd/man/latest/org.freedesktop.resolve1.html
# or man 5 org.freedesktop.resolve1
DEST_RESOLVED = 'org.freedesktop.resolve1'
RESOLVED_MANAGER_IFACE = 'org.freedesktop.resolve1.Manager'
INT_MANAGER = RESOLVED_MANAGER_IFACE
INT_DNSCONFD = 'org.freedesktop.resolve1.Dnsconfd'
PATH_RESOLVED = "/org/freedesktop/resolve1"

# https://networkmanager.dev/docs/api/latest/spec.html
NM_NAME = "org.freedesktop.NetworkManager"
NM_PATH = "/org/freedesktop/NetworkManager"
NM_IFACE = NM_NAME
NM_DNS_PATH = "/org/freedesktop/NetworkManager/DnsManager"
NM_DNS_IFACE = "org.freedesktop.NetworkManager.DnsManager"
NM_DEVICE_IFACE = "org.freedesktop.NetworkManager.Device"
NM_IP4CONFIG_IFACE = "org.freedesktop.NetworkManager.IP4Config"
NM_IP6CONFIG_IFACE = "org.freedesktop.NetworkManager.IP6Config"

__all__ = [ DEST_DNSCONFD, DEST_RESOLVED, INT_MANAGER, INT_DNSCONFD, PATH_RESOLVED,
            NM_NAME, NM_PATH, NM_IFACE, NM_DNS_PATH, NM_DNS_IFACE, NM_DEVICE_IFACE,
            NM_IP4CONFIG_IFACE, NM_IP6CONFIG_IFACE ]
