#include "ip_utilities.h"

#include <stddef.h>
#include <string.h>

int parse_ip_str(const char* str, struct sockaddr_storage* address) {
  struct sockaddr_in* s4 = (struct sockaddr_in*)address;
  struct sockaddr_in6* s6 = (struct sockaddr_in6*)address;

  if (inet_pton(AF_INET, str, &s4->sin_addr) == 1) {
    s4->sin_family = AF_INET;
  } else if (inet_pton(AF_INET6, str, &s6->sin6_addr) == 1) {
    s6->sin6_family = AF_INET6;
  } else {
    return -1;
  }

  return 0;
}

int ip_to_str(struct sockaddr_storage* address, char* buffer) {
  struct sockaddr_in* s4 = (struct sockaddr_in*)address;
  struct sockaddr_in6* s6 = (struct sockaddr_in6*)address;

  if (address->ss_family == AF_INET) {
    if (!inet_ntop(AF_INET, &s4->sin_addr, buffer, INET_ADDRSTRLEN)) {
      return -1;
    }
  } else if (address->ss_family == AF_INET6) {
    if (!inet_ntop(AF_INET6, &s6->sin6_addr, buffer, INET6_ADDRSTRLEN)) {
      return -1;
    }
  } else {
    return -1;
  }

  return 0;
}

void set_default_port(struct sockaddr_storage* address, uint16_t port) {
  struct sockaddr_in* s4 = (struct sockaddr_in*)address;
  struct sockaddr_in6* s6 = (struct sockaddr_in6*)address;

  if (address->ss_family == AF_INET) {
    if (s4->sin_port == 0) {
      s4->sin_port = htons(port);
    }
  } else if (address->ss_family == AF_INET6) {
    if (s6->sin6_port == 0) {
      s6->sin6_port = htons(port);
    }
  }
}

int are_ips_equal(struct sockaddr_storage* a, struct sockaddr_storage* b) {
  if (a->ss_family != b->ss_family) return 0;
  if (a->ss_family == AF_INET) {
    struct sockaddr_in* s4_a = (struct sockaddr_in*)a;
    struct sockaddr_in* s4_b = (struct sockaddr_in*)b;
    return memcmp(&s4_a->sin_addr, &s4_b->sin_addr, sizeof(struct in_addr)) == 0;
  } else if (a->ss_family == AF_INET6) {
    struct sockaddr_in6* s6_a = (struct sockaddr_in6*)a;
    struct sockaddr_in6* s6_b = (struct sockaddr_in6*)b;
    return memcmp(&s6_a->sin6_addr, &s6_b->sin6_addr, sizeof(struct in6_addr)) == 0;
  }
  return 0;
}
