#!/usr/bin/python
#
# Test Network Manager classes

import dbus
import dnsconfd.network_manager

from dnsconfd.network_manager import *

def test_get_object():
    bus = dbus.SystemBus()
    assert(bus)
    nm_d = NetworkManagerDBus(bus)
    assert(nm_d)
    nm_obj = nm_d.get_object(NetworkManagerDBus.DBUS_PATH)
    assert(nm_obj)

def test_property():
    bus = dbus.SystemBus()
    assert(bus)
    nm_d = NetworkManagerDBus(bus)
    assert(nm_d)
    nm_obj = nm_d.get_object(NetworkManagerDBus.DBUS_PATH)
    assert(nm_obj)
    p = DBusProperties(nm_obj, NetworkManagerDBus.DBUS_IFACE)
    assert(p)
    connections = p.Get("ActiveConnections")
    assert(connections)
    assert(len(connections)>0)
    devices = p.Get("Devices")
    assert(devices)
    assert(len(devices)>0)
    #global_dns = p.Get("GlobalDnsConfiguration")

def test_by_interface():
    bus = dbus.SystemBus()
    assert(bus)
    nm_d = NetworkManagerDBus(bus)
    assert(nm_d)
    netif = nm_d.get_device_by_interface("lo")
    assert(netif)
    p = DBusProperties(netif)
    state = p.Get("State")
    assert(state)
    path = p.Get("Path")
    managed = p.Get("Managed")
    assert(managed)
    allp = p.GetAll()
    assert(len(allp)>0)
    reason = p.Get("StateReason")
    intf = allp["Interface"]
    ipiface = allp["IpInterface"]
    mtu = allp["Mtu"]
    print(f"# if: {intf}, ip: {ipiface}, state: {state}, reason: {reason}, managed: {managed}, mtu: {mtu}")
    print(allp.keys())

if __name__ == '__main__':
    test_by_interface()
