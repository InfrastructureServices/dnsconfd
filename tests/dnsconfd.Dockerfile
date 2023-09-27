FROM quay.io/fedora/fedora:38

COPY ./*.noarch.rpm ./
COPY ./dnsconfd_start.service /etc/systemd/system/start.service
RUN dnf install -y --setopt=install_weak_deps=False systemd NetworkManager dhcp-client iproute ./*.rpm openvpn NetworkManager-openvpn
RUN mkdir /etc/openvpn/easy-rsa
RUN systemctl enable dnsconfd start.service

# we will replace the path in code only for testing purposes
# accessing sysfs in the container could be dangerous for the host machine and would require
# running container as privileged
# this may be a bit of a hack but it is safer
RUN sed -i "s#/sys/class/net/#/tmp/is_wireless/#" /usr/lib/python3.11/site-packages/dnsconfd/configuration/interface_configuration.py \
    && echo 'LOG_LEVEL=DEBUG' >> /etc/sysconfig/dnsconfd

ENTRYPOINT /usr/sbin/init
