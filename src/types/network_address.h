#include <netinet/in.h>

#ifndef NETWORK_ADDRESS_H
#define NETWORK_ADDRESS_H

typedef struct {
  struct sockaddr_storage address;
  unsigned char prefix;
} network_address_t;

/**
 * @brief Parses a string in CIDR notation into a network_address_t structure.
 *
 * This function parses an IPv4 or IPv6 address string with a CIDR prefix
 * (e.g., "192.168.1.1/24" or "2001:db8::1/64").
 *
 * @param address_string The string containing the CIDR address to parse.
 * @param addr Pointer to the network_address_t structure to populate.
 * @return 0 on success, -1 on failure (e.g., invalid format, missing prefix).
 */
int network_address_t_from_string(const char *address_string, network_address_t *addr);

int network_address_t_to_reverse_dns(network_address_t *addr, char result[73]);

#endif
