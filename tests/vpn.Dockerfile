FROM quay.io/fedora/fedora:38

RUN dnf install -y openvpn easy-rsa
RUN mkdir /etc/openvpn/easy-rsa && cp -rai /usr/share/easy-rsa/3/* /etc/openvpn/easy-rsa/
RUN cd /etc/openvpn/easy-rsa\
    && ./easyrsa clean-all\
    && EASYRSA_REQ_CN=vpn ./easyrsa --no-pass --batch build-ca\
    && ./easyrsa --batch --no-pass build-server-full vpn\
    && ./easyrsa --batch --no-pass gen-dh
RUN mkdir /etc/openvpn/keys
RUN cd /etc/openvpn/easy-rsa/pki && cp -ai issued/vpn.crt private/vpn.key ca.crt dh*.pem /etc/openvpn/keys/
COPY vpn.conf /etc/openvpn/serverudp.conf

ENTRYPOINT /usr/sbin/openvpn --status-version 2 --suppress-timestamps --cipher AES-256-GCM --data-ciphers AES-256-GCM:AES-128-GCM:AES-256-CBC:AES-128-CBC --config /etc/openvpn/serverudp.conf
