#include "server_uri.h"

#include <arpa/inet.h>
#include <jansson.h>
#include <limits.h>
#include <string.h>
#include <uriparser/Uri.h>

#include "ip_utilities.h"
#include "network_address.h"

static void server_uri_t_dealloc_members(server_uri_t* uri) {
  if (uri->certification_authority) {
    free(uri->certification_authority);
  }
  if (uri->name) {
    free(uri->name);
  }
  if (uri->routing_domains) {
    g_list_free_full(uri->routing_domains, g_free);
  }
  if (uri->networks) {
    g_list_free_full(uri->networks, g_free);
  }
  if (uri->search_domains) {
    g_list_free_full(uri->search_domains, g_free);
  }
}

static void server_uri_t_init(server_uri_t* uri) {
  *uri = (server_uri_t){0};
  uri->dnssec = 1;
}

dns_protocol_t protocol_from_nstring(const char* string, size_t n) {
  if (n != 7) {
    return DNS_PROTOCOLS_END;
  } else if (memcmp(string, "dns+udp", 6) == 0) {
    return DNS_UDP;
  } else if (memcmp(string, "dns+tcp", 6) == 0) {
    return DNS_TCP;
  } else if (memcmp(string, "dns+tls", 6) == 0) {
    return DNS_TLS;
  }

  return DNS_PROTOCOLS_END;
}

const char* dns_protocol_t_to_string(dns_protocol_t protocol) {
  switch (protocol) {
    case DNS_UDP:
      return "dns+udp";
      break;
    case DNS_TCP:
      return "dns+tcp";
      break;
    case DNS_TLS:
      return "dns+tls";
      break;
    default:
      return "unknown";
      break;
  }
}

static int parse_query(UriUriA* parsed_uri, server_uri_t* uri) {
  UriQueryListA* queryList;
  int itemCount;
  long temp_long;
  char* endptr;
  network_address_t* new_net_address;
  char* duplicated_string;

  if (uriDissectQueryMallocA(&queryList, &itemCount, parsed_uri->query.first,
                             parsed_uri->query.afterLast) != URI_SUCCESS) {
    // nothing allocated yet, no free
    return -1;
  }

  for (UriQueryListA* queryListNode = queryList; queryListNode != NULL;
       queryListNode = queryListNode->next) {
    if (queryListNode->value == NULL) {
      goto error;
    }
    if (strcmp(queryListNode->key, "priority") == 0) {
      temp_long = strtol(queryListNode->value, &endptr, 10);
      if (temp_long < INT_MIN || temp_long > INT_MAX || *endptr != 0) {
        goto error;
      }
      uri->priority = temp_long;
    } else if (strcmp(queryListNode->key, "domain") == 0) {
      if ((duplicated_string = strdup(queryListNode->value)) == NULL) {
        goto error;
      }
      uri->routing_domains = g_list_append(uri->routing_domains, duplicated_string);
    } else if (strcmp(queryListNode->key, "search") == 0) {
      if ((duplicated_string = strdup(queryListNode->value)) == NULL) {
        goto error;
      }
      uri->search_domains = g_list_append(uri->search_domains, duplicated_string);
    } else if (strcmp(queryListNode->key, "interface") == 0) {
      if (strlen(queryListNode->value) > IFNAMSIZ) {
        goto error;
      }
      strcpy(uri->interface, queryListNode->value);
    } else if (strcmp(queryListNode->key, "dnssec") == 0) {
      if (queryListNode->value[0] == '0') {
        uri->dnssec = 0;
      }
    } else if (strcmp(queryListNode->key, "ca") == 0) {
      if ((uri->certification_authority = strdup(queryListNode->value)) == NULL) {
        goto error;
      }
    } else if (strcmp(queryListNode->key, "name") == 0) {
      if ((uri->name = strdup(queryListNode->value)) == NULL) {
        goto error;
      }
    } else if (strcmp(queryListNode->key, "network") == 0) {
      new_net_address = malloc(sizeof(network_address_t));
      if (new_net_address == NULL) {
        goto error;
      }
      if (network_address_t_from_string(queryListNode->value, new_net_address) != 0) {
        free(new_net_address);
        goto error;
      }
      uri->networks = g_list_append(uri->networks, new_net_address);
    }
  }

  uriFreeQueryListA(queryList);
  return 0;
error:
  server_uri_t_dealloc_members(uri);
  uriFreeQueryListA(queryList);
  return -1;
}

int server_uri_t_init_from_string(char* uri_string, server_uri_t* uri) {
  char ip_str[INET6_ADDRSTRLEN];
  UriUriA parsed_uri;
  size_t temp_length;
  long temp_long;
  struct sockaddr_in* s4;
  struct sockaddr_in6* s6;

  if (uriParseSingleUriA(&parsed_uri, uri_string, NULL) != URI_SUCCESS) {
    return -1;
  }

  server_uri_t_init(uri);

  temp_length = parsed_uri.scheme.afterLast - parsed_uri.scheme.first;

  if (temp_length > 0 && (uri->protocol = protocol_from_nstring(
                              parsed_uri.scheme.first, temp_length)) == DNS_PROTOCOLS_END) {
    return -1;
  }

  s4 = (struct sockaddr_in*)&uri->address;
  s6 = (struct sockaddr_in6*)&uri->address;

  temp_length = parsed_uri.hostText.afterLast - parsed_uri.hostText.first;
  if (temp_length > INET6_ADDRSTRLEN) {
    return -1;
  }
  memcpy(ip_str, parsed_uri.hostText.first, temp_length);
  ip_str[temp_length] = 0;

  if (parse_ip_str(ip_str, &uri->address) != 0) {
    return -1;
  }

  temp_length = parsed_uri.portText.afterLast - parsed_uri.portText.first;
  if (temp_length > 0) {
    temp_long = strtol(parsed_uri.portText.first, NULL, 10);
    if (temp_long < 0 || temp_long > 65535) {
      return -1;
    }
    if (uri->address.ss_family == AF_INET) {
      s4->sin_port = htons((uint16_t)temp_long);
    } else {
      s6->sin6_port = htons((uint16_t)temp_long);
    }
  }

  if (parsed_uri.query.afterLast - parsed_uri.query.first > 0 &&
      parse_query(&parsed_uri, uri) != 0) {
    return -1;
  }
  return 0;
}

void server_uri_t_destroy(void* data) {
  server_uri_t* uri = (server_uri_t*)data;
  if (uri) {
    server_uri_t_dealloc_members(uri);
    free(uri);
  }
}

static int parse_json_port_field(json_t* field, server_uri_t* uri) {
  json_int_t numeric_value;
  struct sockaddr_in* s4 = (struct sockaddr_in*)&uri->address;
  struct sockaddr_in6* s6 = (struct sockaddr_in6*)&uri->address;

  if (!json_is_integer(field)) {
    return -1;
  }
  numeric_value = json_integer_value(field);
  if (numeric_value < 0 || numeric_value > 65535) {
    return -1;
  }
  if (uri->address.ss_family == AF_INET) {
    s4->sin_port = htons((uint16_t)numeric_value);
  } else {
    s6->sin6_port = htons((uint16_t)numeric_value);
  }
  return 0;
}

static int parse_json_address_field(json_t* field, server_uri_t* uri) {
  if (field == NULL || !json_is_string(field)) {
    return -1;
  }

  return parse_ip_str(json_string_value(field), &uri->address);
}

static int parse_json_protocol_field(json_t* field, server_uri_t* uri) {
  if (!json_is_string(field)) {
    return -1;
  }

  uri->protocol = protocol_from_nstring(json_string_value(field), json_string_length(field));
  if (uri->protocol == DNS_PROTOCOLS_END) {
    return -1;
  }
  return 0;
}

static int parse_json_priority_field(json_t* field, server_uri_t* uri) {
  json_int_t numeric_value;

  if (!json_is_integer(field)) {
    return -1;
  }
  numeric_value = json_integer_value(field);
  if (numeric_value < INT_MIN || numeric_value > INT_MAX) {
    return -1;
  }
  uri->priority = (int)numeric_value;
  return 0;
}

static int parse_json_interface_field(json_t* field, server_uri_t* uri) {
  const char* str_val;

  if (!json_is_string(field)) {
    return -1;
  }
  str_val = json_string_value(field);
  if (strlen(str_val) >= IFNAMSIZ) {
    return -1;
  }
  strcpy(uri->interface, str_val);
  return 0;
}

static int parse_json_dnssec_field(json_t* field, server_uri_t* uri) {
  if (json_is_boolean(field)) {
    uri->dnssec = json_is_true(field) ? 1 : 0;
  } else if (json_is_integer(field)) {
    uri->dnssec = json_integer_value(field) != 0;
  } else if (json_is_string(field)) {
    if (strcmp(json_string_value(field), "0") == 0) {
      uri->dnssec = 0;
    }
  } else {
    return -1;
  }
  return 0;
}

static int parse_json_ca_field(json_t* field, server_uri_t* uri) {
  if (!json_is_string(field)) {
    return -1;
  }
  uri->certification_authority = strdup(json_string_value(field));
  if (!uri->certification_authority) {
    return -1;
  }
  return 0;
}

static int parse_json_name_field(json_t* field, server_uri_t* uri) {
  if (!json_is_string(field)) {
    return -1;
  }
  uri->name = strdup(json_string_value(field));
  if (!uri->name) {
    return -1;
  }
  return 0;
}

static int parse_json_string_list(json_t* field, GList** list) {
  size_t d_idx;
  json_t* d_val;
  char* d_dup;

  if (!json_is_array(field)) {
    return -1;
  }

  json_array_foreach(field, d_idx, d_val) {
    if (!json_is_string(d_val)) {
      return -1;
    }
    d_dup = strdup(json_string_value(d_val));
    if (d_dup == NULL) {
      return -1;
    }
    *list = g_list_append(*list, d_dup);
  }
  return 0;
}

static int parse_json_domains_field(json_t* field, server_uri_t* uri) {
  return parse_json_string_list(field, &uri->routing_domains);
}

static int parse_json_search_domains_field(json_t* field, server_uri_t* uri) {
  return parse_json_string_list(field, &uri->search_domains);
}

static int parse_json_networks_field(json_t* field, server_uri_t* uri) {
  size_t n_idx;
  json_t* n_val;
  network_address_t* net;

  if (!json_is_array(field)) {
    return -1;
  }

  json_array_foreach(field, n_idx, n_val) {
    if (!json_is_string(n_val)) {
      return -1;
    }
    net = malloc(sizeof(network_address_t));
    if (!net) {
      return -1;
    }
    if (network_address_t_from_string((char*)json_string_value(n_val), net) != 0) {
      free(net);
      return -1;
    }
    uri->networks = g_list_append(uri->networks, net);
  }
  return 0;
}

GList* server_uri_t_list_from_json(const char* server_list) {
  json_t* root;
  json_error_t error;
  GList* list = NULL;
  size_t index;
  json_t* value;
  server_uri_t* uri;
  json_t* field;
  size_t i;

  struct {
    const char* key;
    int (*parser)(json_t*, server_uri_t*);
  } optional_fields[] = {
      {"port", parse_json_port_field},         {"protocol", parse_json_protocol_field},
      {"priority", parse_json_priority_field}, {"interface", parse_json_interface_field},
      {"dnssec", parse_json_dnssec_field},     {"ca", parse_json_ca_field},
      {"name", parse_json_name_field},         {"routing_domains", parse_json_domains_field},
      {"search_domains", parse_json_search_domains_field},
      {"networks", parse_json_networks_field},
  };

  root = json_loads(server_list, 0, &error);
  if (!root) return NULL;

  if (!json_is_array(root)) {
    json_decref(root);
    return NULL;
  }

  json_array_foreach(root, index, value) {
    if (!json_is_object(value)) {
      goto error;
    }

    uri = malloc(sizeof(server_uri_t));
    if (!uri) {
      goto error;
    }
    server_uri_t_init(uri);

    field = json_object_get(value, "address");
    if (parse_json_address_field(field, uri)) {
      server_uri_t_destroy(uri);
      goto error;
    }

    // parsing of optional fields is the same for all of them, that is why we have
    // helping struct to list their keys and parsing functions
    for (i = 0; i < sizeof(optional_fields) / sizeof(optional_fields[0]); i++) {
      field = json_object_get(value, optional_fields[i].key);
      if (field != NULL && optional_fields[i].parser(field, uri) != 0) {
        server_uri_t_destroy(uri);
        goto error;
      }
    }

    list = g_list_append(list, uri);
  }

  json_decref(root);
  return list;

error:
  json_decref(root);
  g_list_free_full(list, server_uri_t_destroy);
  return NULL;
}

static gint compare_servers(gconstpointer a, gconstpointer b) {
  server_uri_t* server_a = (server_uri_t*)a;
  server_uri_t* server_b = (server_uri_t*)b;
  int temp;

  if (server_a == NULL) {
    return server_b == NULL ? 0 : 1;
  } else if (server_b == NULL) {
    return -1;
  }

  temp = server_b->priority - server_a->priority;
  if (temp == 0) {
    temp = server_b->protocol - server_a->protocol;
    if (temp != 0) {
      return temp;
    }
    return (gint)(server_b->dnssec - server_a->dnssec);
  }

  return temp;
}

static void append_server(GHashTable* hash_table, const char* domain, server_uri_t* server) {
  GList* server_sublist = (GList*)g_hash_table_lookup(hash_table, domain);

  if (server_sublist) {
    // server_sublist is never NULL here, but to prevent warnings assign return
    // value of g_list_append back to server_sublist variable
    server_sublist = g_list_append(server_sublist, server);
  } else {
    server_sublist = g_list_append(NULL, server);
    g_hash_table_insert(hash_table, g_strdup(domain), server_sublist);
  }
}

GHashTable* server_list_to_hash_table(GList* server_list) {
  GHashTable* hash_table;
  GList* server_iter;
  GList* sorted_list;
  server_uri_t* server;
  GList* domain_iter;
  const char* domain;
  network_address_t* network;
  GHashTableIter iter;
  gpointer value;
  char domain_buffer[73];

  hash_table = g_hash_table_new_full(g_str_hash, g_str_equal, g_free, (GDestroyNotify)g_list_free);

  // Iterate through all servers in the input list
  for (server_iter = server_list; server_iter != NULL; server_iter = server_iter->next) {
    server = (server_uri_t*)server_iter->data;

    // Iterate through all routing domains of this server
    for (domain_iter = server->routing_domains; domain_iter != NULL;
         domain_iter = domain_iter->next) {
      domain = (const char*)domain_iter->data;
      append_server(hash_table, domain, server);
    }

    for (domain_iter = server->networks; domain_iter != NULL; domain_iter = domain_iter->next) {
      network = (network_address_t*)domain_iter->data;
      if (network_address_t_to_reverse_dns(network, domain_buffer)) {
        g_hash_table_destroy(hash_table);
        return NULL;
      }
      append_server(hash_table, domain_buffer, server);
    }
  }

  // sort every list in hash table with compare_servers function
  g_hash_table_iter_init(&iter, hash_table);
  while (g_hash_table_iter_next(&iter, NULL, &value)) {
    // the copy here is neccessary, because g_hash_table_iter_replace frees
    // the original list
    sorted_list = g_list_sort(g_list_copy((GList*)value), compare_servers);
    g_hash_table_iter_replace(&iter, sorted_list);
  }

  return hash_table;
}

json_t* server_uri_to_json(server_uri_t* server) {
  char addr_str[INET6_ADDRSTRLEN];
  uint16_t port;
  json_t* obj = json_object();

  // Address
  ip_to_str(&server->address, addr_str);

  json_object_set_new(obj, "address", json_string(addr_str));

  // Port
  if (server->address.ss_family == AF_INET) {
    port = ntohs(((struct sockaddr_in*)&server->address)->sin_port);
  } else {
    port = ntohs(((struct sockaddr_in6*)&server->address)->sin6_port);
  }
  json_object_set_new(obj, "port", json_integer(port));

  // Name
  if (server->name)
    json_object_set_new(obj, "name", json_string(server->name));
  else
    json_object_set_new(obj, "name", json_null());

  // Routing domains
  json_t* domains_arr = json_array();
  for (GList* l = server->routing_domains; l != NULL; l = l->next) {
    json_array_append_new(domains_arr, json_string((char*)l->data));
  }
  json_object_set_new(obj, "routing_domains", domains_arr);

  // Search domains
  json_t* search_arr = json_array();
  for (GList* l = server->search_domains; l != NULL; l = l->next) {
    json_array_append_new(search_arr, json_string((char*)l->data));
  }
  json_object_set_new(obj, "search_domains", search_arr);

  // Interface
  if (server->interface[0] != '\0')
    json_object_set_new(obj, "interface", json_string(server->interface));
  else
    json_object_set_new(obj, "interface", json_null());

  // Protocol
  json_object_set_new(obj, "protocol", json_string(dns_protocol_t_to_string(server->protocol)));

  // DNSSEC
  json_object_set_new(obj, "dnssec", json_boolean(server->dnssec));

  // Networks
  json_t* networks_arr = json_array();
  for (GList* l = server->networks; l != NULL; l = l->next) {
    network_address_t* net = (network_address_t*)l->data;
    char net_str[INET6_ADDRSTRLEN + 5];  // + /prefix
    char ip_str[INET6_ADDRSTRLEN];
    ip_to_str(&net->address, ip_str);
    snprintf(net_str, sizeof(net_str), "%s/%d", ip_str, net->prefix);
    json_array_append_new(networks_arr, json_string(net_str));
  }
  json_object_set_new(obj, "networks", networks_arr);

  return obj;
}
