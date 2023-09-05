FROM quay.io/fedora/fedora:38

RUN dnf install -y systemd NetworkManager NetworkManager-tui iproute
RUN dnf remove -y systemd-resolved
COPY ./*.noarch.rpm ./
RUN dnf install -y ./*.rpm
RUN echo "RESOLV_CONF_PATH=/etc/resolv.conf" >> /etc/sysconfig/dnsconfd

ENTRYPOINT /usr/sbin/init
