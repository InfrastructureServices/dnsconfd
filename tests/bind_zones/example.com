$ORIGIN example.com.
$TTL 86400
@       IN      SOA     dns1.example.com.       hostmaster.example.com. (
                        2001062501 ; serial                     
                        21600      ; refresh after 6 hours                     
                        3600       ; retry after 1 hour                     
                        604800     ; expire after 1 week                     
                        86400 )    ; minimum TTL of 1 day  


        IN      NS      dns1.example.com.
dns1    IN      A       192.168.6.3
server  IN      A       192.168.6.5
not-working IN  A       192.168.6.6
$INCLUDE "Kexample.com.+008+42430.key"
$INCLUDE "Kexample.com.+008+64519.key"
