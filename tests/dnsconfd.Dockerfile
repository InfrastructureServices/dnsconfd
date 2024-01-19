FROM quay.io/fedora/fedora:latest

COPY ./*.noarch.rpm ./
RUN dnf install -y --setopt=install_weak_deps=False --setopt=tsflags=nodocs systemd \
    NetworkManager dhcp-client iproute ./*.rpm openvpn NetworkManager-openvpn sssd-client

# we will replace the path in code only for testing purposes
# accessing sysfs in the container could be dangerous for the host machine and would require
# running container as privileged
# this may be a bit of a hack but it is safer
RUN sed -i "s#/sys/class/net/#/tmp/is_wireless/#" /usr/lib/python3.12/site-packages/dnsconfd/configuration/interface_configuration.py \
    && echo 'LOG_LEVEL=DEBUG' >> /etc/sysconfig/dnsconfd

RUN printf "[main]\ndns=systemd-resolved\nrc-manager=unmanaged\n" > /etc/NetworkManager/conf.d/dnsconf.conf
# because of our internal network, disable unbound anchor
RUN printf "DISABLE_UNBOUND_ANCHOR=yes" >> /etc/sysconfig/unbound
# enable dnsconfd
RUN systemctl enable dnsconfd

ENTRYPOINT /usr/sbin/init
