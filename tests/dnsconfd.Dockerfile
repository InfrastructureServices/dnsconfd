FROM scratch

COPY ./baseroot /
COPY ./*.rpm ./
RUN dnf install -y --setopt=install_weak_deps=False --setopt=tsflags=nodocs systemd \
    NetworkManager iproute ./*.rpm openvpn NetworkManager-openvpn sssd-client \
    polkit bind-utils bind-dnssec-utils dbus-tools net-tools rsyslog tcpdump procps-ng python3-idna vim crypto-policies-scripts less gdb

RUN echo 'LOG_LEVEL=DEBUG' >> /etc/sysconfig/dnsconfd

# increase unbound logging
RUN sed -i "s/verbosity.*/verbosity: 5/g" /etc/unbound/unbound.conf

RUN printf "[main]\ndns=dnsconfd\n[logging]\ndomains=ALL:TRACE\n" > /etc/NetworkManager/conf.d/dnsconfd.conf
# enable dnsconfd
RUN systemctl enable dnsconfd

# this is neccessary because of https://github.com/systemd/systemd/issues/29860
# first 13 lines do not contain sandboxing options that trigger fail because
# of missing CAP_SYS_ADMIN
RUN head -n 13 /usr/lib/systemd/system/polkit.service > /polkit.tmp; cat /polkit.tmp > /usr/lib/systemd/system/polkit.service

ENTRYPOINT /usr/sbin/init
