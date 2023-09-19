FROM quay.io/fedora/fedora:38

RUN dnf install -y dhcp-server

COPY ./dhcpd.conf /etc/dhcp/dhcpd.conf

ENTRYPOINT ["/usr/sbin/dhcpd", "-f", "-cf" , "/etc/dhcp/dhcpd.conf"]
