"""DBus constants module."""

# Our future dbus service name. Not yet used.
DNSCONFD_NAME = 'com.redhat.dnsconfd'

# Implements systemd-resolved interfaces defined at:
# https://www.freedesktop.org/software/systemd/man/latest/org.freedesktop.resolve1.html
# or man 5 org.freedesktop.resolve1
RESOLVED_NAME = 'org.freedesktop.resolve1'
MANAGER_IFACE =  RESOLVED_NAME+'.Manager'
DNSCONFD_IFACE = RESOLVED_NAME+'.Dnsconfd'
RESOLVED_PATH = "/org/freedesktop/resolve1"

# https://networkmanager.dev/docs/api/latest/spec.html
NM_NAME = "org.freedesktop.NetworkManager"
NM_PATH = "/org/freedesktop/NetworkManager/DnsManager"
NM_IFACE = "org.freedesktop.NetworkManager.DnsManager"
