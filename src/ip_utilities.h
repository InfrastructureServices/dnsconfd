#include <arpa/inet.h>

#ifndef IP_UTILITIES_H
#define IP_UTILITIES_H

int parse_ip_str(const char *str, struct sockaddr_storage *address);

int ip_to_str(struct sockaddr_storage *address, char *buffer);

void set_default_port(struct sockaddr_storage *address, uint16_t port);

int are_ips_equal(struct sockaddr_storage *a, struct sockaddr_storage *b);

#endif /* IP_UTILITIES_H */
