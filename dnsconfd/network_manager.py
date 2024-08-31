import subprocess
import dbus


class NetworkManager(object):
    NM_CONF_D = "/etc/NetworkManager/conf.d"
    NM_CONF = NM_CONF_D + "/dnsconfd.conf"
    HEADER = "## This file is maintained by " \
             "dnsconfd tool, do not edit by hand!\n"

    @staticmethod
    def reload():
        """ Perform reload of Network Manager """
        subprocess.run(["systemctl", "reload", "NetworkManager"],
                       capture_output=True,
                       check=True)

    def enable(self) -> bool:
        """ Enables dnsconfd in Network Manager. Requires root privileges. """
        try:
            with open(self.NM_CONF, "w") as f:
                # TODO: have own plugin in NM
                f.writelines([self.HEADER,
                              "[main]\n",
                              "dns=systemd-resolved\n",
                              "rc-manager=unmanaged\n"])
        except OSError as e:
            print(f"Unable to configure network manager: {e}")
            return False
        self.reload()
        return True

    def disable(self) -> bool:
        """ Disables dnsconfd in Network Manager. Requires root privileges. """
        try:
            with open(self.NM_CONF, "w") as f:
                f.writelines([self.HEADER])
        except OSError as e:
            print(f"Unable to configure network manager: {e}")
            return False
        self.reload()

class DBusProperties(object):
    """Helper class wrapping working with DBus properties."""

    @staticmethod
    def get_property(obj: dbus.proxies.ProxyObject, iface: str, key: str):
        """Get single property."""

        properties = dbus.Interface(obj, dbus.PROPERTIES_IFACE)
        return properties.Get(iface, key)

    @staticmethod
    def get_properties(obj: dbus.proxies.ProxyObject, iface: str):
        """Get all properties dictionary."""

        properties = dbus.Interface(obj, dbus.PROPERTIES_IFACE)
        return properties.GetAll(iface)

    @staticmethod
    def set_property(obj: dbus.proxies.ProxyObject, iface: str, key: str, val):
        """Change single property."""

        properties = dbus.Interface(obj, dbus.PROPERTIES_IFACE)
        return properties.Set(iface, key, val)

    def __init__(self, obj, interface=None):
        """Create helper object instance.

        First parameter can be dbus.Interface or proxy object."""
        if isinstance(obj, dbus.Interface):
            self.proxy_object = obj.proxy_object
            self.dbus_interface = obj.dbus_interface
        elif isinstance(obj, dbus.proxies.ProxyObject) and interface:
            self.proxy_object = obj
            self.dbus_interface = interface
        else:
            raise(TypeError("unsupported type of obj parameter"))

    def Get(self, key: str):
        return self.get_property(self.proxy_object,
                                 self.dbus_interface,
                                 key)

    def GetAll(self):
        return self.get_properties(self.proxy_object,
                                   self.dbus_interface)

    def Set(self, key: str, val):
        return self.set_property(self.proxy_object,
                                 self.dbus_interface,
                                 key, val)


class NetworkManagerDBus(object):
    DBUS_NAME = 'org.freedesktop.NetworkManager'
    DBUS_IFACE = DBUS_NAME
    DBUS_PATH = '/org/freedesktop/NetworkManager'
    DBUS_DEVICE_IFACE = 'org.freedesktop.NetworkManager.Device'
    DBUS_IP4CONFIG_IFACE = 'org.freedesktop.NetworkManager.IP4Config'
    DBUS_IP6CONFIG_IFACE = 'org.freedesktop.NetworkManager.IP6Config'

    def __init__(self, bus: dbus.Bus):
        self.bus = bus

    def get_object(self, path: str):
        return self.bus.get_object(self.DBUS_NAME, path)

    def get_nm_interface(self):
        obj = self.get_object(self.DBUS_PATH)
        return dbus.Interface(obj, self.DBUS_IFACE)

    def get_device_by_interface(self, ifname):
        """Get DBus proxy object of Device identified by ifname."""
        nm_interface = self.get_nm_interface()
        device_path = nm_interface.GetDeviceByIpIface(ifname)
        device_object = self.get_object(device_path)
        dev_int = dbus.Interface(device_object,
                                 self.DBUS_DEVICE_IFACE)
        return dev_int
