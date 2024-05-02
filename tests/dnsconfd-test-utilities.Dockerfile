FROM quay.io/fedora/fedora:38

RUN dnf install -y --setopt=tsflags=nodocs --setopt=install_weak_deps=False dhcp-server \
    dnsmasq openvpn easy-rsa && dnf -y clean all

# DHCP PART
COPY dhcpd-common.conf dhcpd-empty.conf /etc/dhcp/

# VPN PART
RUN mkdir /etc/openvpn/easy-rsa && cp -rai /usr/share/easy-rsa/3/* /etc/openvpn/easy-rsa/
RUN cd /etc/openvpn/easy-rsa\
    && ./easyrsa clean-all\
    && EASYRSA_REQ_CN=vpn ./easyrsa --no-pass --batch build-ca\
    && ./easyrsa --batch --no-pass build-server-full vpn\
    && ./easyrsa --batch --no-pass gen-dh
COPY vpn.conf /etc/openvpn/serverudp.conf

COPY dhcp_entry.sh vpn_entry.sh dnsmasq_entry.sh /usr/bin/
