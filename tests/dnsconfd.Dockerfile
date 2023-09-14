FROM quay.io/fedora/fedora:38

RUN dnf install -y systemd NetworkManager
RUN dnf remove -y systemd-resolved
COPY ./*.noarch.rpm ./
COPY ./dnsconfd_start.service /etc/systemd/system/start.service
RUN dnf install -y ./*.rpm
RUN systemctl enable dnsconfd
RUN echo "RESOLV_CONF_PATH=/etc/resolv.conf" >> /etc/sysconfig/dnsconfd

RUN systemctl enable start.service

ENTRYPOINT /usr/sbin/init
