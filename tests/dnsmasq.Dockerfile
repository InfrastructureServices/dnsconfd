FROM quay.io/fedora/fedora:38

RUN dnf install -y dnsmasq

RUN echo "no-resolv" >> /etc/dnsmasq.conf
RUN echo "no-hosts" >> /etc/dnsmasq.conf

ENTRYPOINT ["/usr/sbin/dnsmasq", "-d"]
