#include <linux/if.h>
#include <netinet/in.h>
#include <gio/gio.h>
#include <jansson.h>

#ifndef SERVER_URI_H
#define SERVER_URI_H

typedef enum {
  DNS_UDP = 0,
  DNS_TCP,
  DNS_TLS,
  DNS_PROTOCOLS_END,
} dns_protocol_t;

typedef struct {
  struct sockaddr_storage address;
  int priority;
  char interface[IFNAMSIZ];
  unsigned char dnssec;
  dns_protocol_t protocol;
  char* certification_authority;
  char* name;
  GList* routing_domains;
  GList* search_domains;
  GList* networks;
} server_uri_t;

int server_uri_t_init_from_string(char* uri_string, server_uri_t* uri);

GList* server_uri_t_list_from_json(const char* server_list);

void server_uri_t_destroy(void* uri);

const char *dns_protocol_t_to_string(dns_protocol_t protocol);

GHashTable *server_list_to_hash_table(GList *server_list);

json_t* server_uri_to_json(server_uri_t* server);

dns_protocol_t protocol_from_nstring(const char* string, size_t n);

void server_uri_t_list_replace_elements_with_copies(GList* list);

#endif
