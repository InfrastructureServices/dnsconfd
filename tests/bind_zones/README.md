Commands used:

``dnssec-keygen -a RSASHA256 -b 2048 -n ZONE com``

``dnssec-keygen -f KSK -a RSASHA256 -b 4096 -n ZONE com``

``dnssec-signzone -3 $(head -c 1000 /dev/random | sha256sum | cut -b 1-16) -A -N INCREMENT -o com -t com``

not-working.example.com RRSIG was manually broken so we can test validation failure
