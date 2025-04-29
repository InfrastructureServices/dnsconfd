FROM quay.io/fedora/fedora:40

RUN dnf install -y --setopt=tsflags=nodocs --setopt=install_weak_deps=False dhcp-server \
    dnsmasq which bc openvpn easy-rsa bind bind-utils bind-dnssec-utils openssl iproute iputils ratools vim nftables && dnf -y clean all

# DHCP PART
COPY dhcpd-common.conf dhcpd-empty.conf /etc/dhcp/

COPY ratool.conf /ratool.conf

# VPN PART
RUN mkdir /etc/openvpn/easy-rsa && cp -rai /usr/share/easy-rsa/3/* /etc/openvpn/easy-rsa/
RUN cd /etc/openvpn/easy-rsa\
    && ./easyrsa clean-all\
    && EASYRSA_REQ_CN=vpn ./easyrsa --no-pass --batch build-ca\
    && ./easyrsa --batch --no-pass build-server-full vpn\
    && ./easyrsa --batch --no-pass gen-dh
COPY vpn.conf /etc/openvpn/serverudp.conf

COPY named.conf /etc/named.conf
COPY named2.conf /etc/named2.conf
COPY bind_zones named_certs/my_signed_cert.pem named_certs/my_private_key.pem named_certs/my_signed_cert2.pem named_certs/my_private_key2.pem /etc/named/
RUN chown named /etc/named/my_signed_cert.pem /etc/named/my_private_key.pem /etc/named/my_signed_cert2.pem /etc/named/my_private_key2.pem

COPY dhcp_entry.sh vpn_entry.sh dnsmasq_entry.sh bind_entry.sh ratool_entry.sh /usr/bin/
