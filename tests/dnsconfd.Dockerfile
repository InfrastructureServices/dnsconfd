FROM quay.io/fedora/fedora:41

COPY ./*.noarch.rpm ./
RUN dnf install -y --setopt=install_weak_deps=False --setopt=tsflags=nodocs systemd \
    NetworkManager dhcp-client iproute ./*.rpm openvpn NetworkManager-openvpn sssd-client polkit bind-utils bind-dnssec-utils

# we will replace the path in code only for testing purposes
# accessing sysfs in the container could be dangerous for the host machine and would require
# running container as privileged
# this may be a bit of a hack but it is safer
RUN sed -i "s#/sys/class/net/#/tmp/is_wireless/#" /usr/lib/python3.12/site-packages/dnsconfd/network_objects/interface_configuration.py \
    && echo 'LOG_LEVEL=DEBUG' >> /etc/sysconfig/dnsconfd

RUN printf "[main]\ndns=systemd-resolved\nrc-manager=unmanaged\n" > /etc/NetworkManager/conf.d/dnsconfd.conf
# enable dnsconfd
RUN systemctl enable dnsconfd

RUN printf "[Unit]\nDescription=Start service\n[Service]\nExecStart=dnsconfd config take_resolvconf\n[Install]\nWantedBy=multi-user.target\n" > /etc/systemd/system/take_resolv.service

RUN systemctl enable take_resolv

# this is neccessary because of https://github.com/systemd/systemd/issues/29860
# first 13 lines do not contain sandboxing options that trigger fail because
# of missing CAP_SYS_ADMIN
RUN head -n 13 /usr/lib/systemd/system/polkit.service > /polkit.tmp; cat /polkit.tmp > /usr/lib/systemd/system/polkit.service

ENTRYPOINT /usr/sbin/init
