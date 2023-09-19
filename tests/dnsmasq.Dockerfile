FROM quay.io/fedora/fedora:38

RUN dnf install -y dnsmasq

RUN printf "no-resolv\nno-hosts\n" >> /etc/dnsmasq.conf

ENTRYPOINT ["/usr/sbin/dnsmasq", "-d"]
