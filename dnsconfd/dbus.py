"""DBus constants module."""

# Our future dbus service name. Not yet used.
DEST_DNSCONFD = 'com.redhat.dnsconfd'

# Implements systemd-resolved interfaces defined at:
# https://www.freedesktop.org/software/systemd/man/latest/org.freedesktop.resolve1.html
# or man 5 org.freedesktop.resolve1
DEST_RESOLVED = 'org.freedesktop.resolve1'
INT_MANAGER = 'org.freedesktop.resolve1.Manager'
INT_DNSCONFD = 'org.freedesktop.resolve1.Dnsconfd'
PATH_RESOLVED = "/org/freedesktop/resolve1"

# https://networkmanager.dev/docs/api/latest/spec.html
NM_NAME = "org.freedesktop.NetworkManager"
NM_PATH = "/org/freedesktop/NetworkManager/DnsManager"
NM_INTERFACE = "org.freedesktop.NetworkManager.DnsManager"

