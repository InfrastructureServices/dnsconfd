#include "network_address.h"

#include <arpa/inet.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int network_address_t_from_string(const char* address_string, network_address_t* addr) {
  char ip_str[INET6_ADDRSTRLEN];
  const char* ip_part = address_string;
  int prefix;
  long raw_prefix;
  char* endptr;
  struct sockaddr_in* s4;
  struct sockaddr_in6* s6;
  const char* slash = strchr(address_string, '/');

  if (!slash) {
    return -1;
  }

  size_t len = slash - address_string;
  if (len >= sizeof(ip_str)) {
    return -1;
  }
  strncpy(ip_str, address_string, len);
  ip_str[len] = '\0';
  ip_part = ip_str;

  raw_prefix = strtol(slash + 1, &endptr, 10);
  if (*endptr != '\0' || raw_prefix < 0 || raw_prefix > 128) {
    return -1;
  }
  prefix = (int)raw_prefix;

  s4 = (struct sockaddr_in*)&addr->address;
  s6 = (struct sockaddr_in6*)&addr->address;

  // Try IPv4
  if (inet_pton(AF_INET, ip_part, &s4->sin_addr) == 1) {
    if (prefix > 32) {
      return -1;
    }
    s4->sin_family = AF_INET;
    addr->prefix = (unsigned char)prefix;
    return 0;
  }

  // Try IPv6
  if (inet_pton(AF_INET6, ip_part, &s6->sin6_addr) == 1) {
    // We do not have to check for prefix here as we already know it is > 0 and <= 128
    s6->sin6_family = AF_INET6;
    addr->prefix = (unsigned char)prefix;
    return 0;
  }

  return -1;
}

static void reverse_dns_ipv4(struct sockaddr_in* s4, unsigned char prefix, char* result) {
  unsigned char* bytes;
  char buf[8];
  int nibbles = prefix / 8;
  // Cap octets at 4 for IPv4
  if (nibbles > 4) nibbles = 4;

  // Allocate memory: 4 blocks of up to 3 digits + 3 dots + "in-addr.arpa" (12) + null terminator
  // Max: "255.255.255.255.in-addr.arpa" -> 15 + 1 + 12 + 1 = 29.
  result[0] = '\0';

  bytes = (unsigned char*)&s4->sin_addr.s_addr;

  for (int i = nibbles - 1; i >= 0; i--) {
    snprintf(buf, sizeof(buf), "%d.", bytes[i]);
    strcat(result, buf);
  }
  strcat(result, "in-addr.arpa");
}

static void reverse_dns_ipv6(struct sockaddr_in6* s6, unsigned char prefix, char* result) {
  unsigned char* bytes;
  char buf[4];
  int nibbles = prefix / 4;
  // Cap nibbles at 32 for IPv6 (128 bits / 4)
  if (nibbles > 32) nibbles = 32;

  // Allocate memory: 32 nibbles + 32 dots + "ip6.arpa" (8) + null terminator
  // Max: 32 * 2 + 8 + 1 = 73.
  result[0] = '\0';

  bytes = s6->sin6_addr.s6_addr;

  for (int i = nibbles - 1; i >= 0; i--) {
    int byte_idx = i / 2;
    int val;
    if (i % 2 == 0) {
      // Even index: high nibble
      val = (bytes[byte_idx] >> 4) & 0x0F;
    } else {
      // Odd index: low nibble
      val = bytes[byte_idx] & 0x0F;
    }
    snprintf(buf, sizeof(buf), "%x.", val);
    strcat(result, buf);
  }
  strcat(result, "ip6.arpa");
}

int network_address_t_to_reverse_dns(network_address_t* addr, char result[73]) {
  struct sockaddr_in* s4 = (struct sockaddr_in*)&addr->address;
  struct sockaddr_in6* s6 = (struct sockaddr_in6*)&addr->address;

  if (s4->sin_family == AF_INET) {
    reverse_dns_ipv4(s4, addr->prefix, result);
    return 0;
  } else if (s6->sin6_family == AF_INET6) {
    reverse_dns_ipv6(s6, addr->prefix, result);
    return 0;
  }

  return -1;
}
