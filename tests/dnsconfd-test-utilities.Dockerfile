FROM quay.io/fedora/fedora:38

RUN dnf install -y --setopt=tsflags=nodocs --setopt=install_weak_deps=False dhcp-server \
    dnsmasq openvpn easy-rsa bind bind-utils bind-dnssec-utils openssl && dnf -y clean all

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

COPY named.conf /etc/named.conf
COPY bind_zones /etc/named/
COPY named_certs/my_signed_cert.pem named_certs/my_private_key.pem /etc/named/
RUN chown named /etc/named/my_signed_cert.pem
RUN chown named /etc/named/my_private_key.pem

COPY dhcp_entry.sh vpn_entry.sh dnsmasq_entry.sh bind_entry.sh /usr/bin/
