#include "unbound_manager.h"

#include <arpa/inet.h>
#include <gio/gio.h>
#include <glib.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <unistd.h>

#include "fsm/fsm.h"
#include "ip_utilities.h"
#include "types/server_uri.h"

static GList *get_used_servers(GList *servers, dnsconfd_mode_t mode, const char *domain) {
  GList *used_servers = NULL;
  server_uri_t *cur_server = ((server_uri_t *)servers->data);
  int max_priority = cur_server->priority;
  dns_protocol_t max_protocol = cur_server->protocol;
  unsigned char dnssec = cur_server->dnssec;

  for (; servers != NULL; servers = servers->next) {
    cur_server = ((server_uri_t *)servers->data);
    if (cur_server->priority < max_priority || cur_server->protocol < max_protocol ||
        cur_server->dnssec != dnssec) {
      break;
    }
    // if this server can not be used globally and we are in strict mode, then
    // skip it
    if (cur_server->interface[0] != '\0') {
      if ((mode > MODE_BACKUP && strcmp(domain, ".") == 0) || mode == MODE_EXCLUSIVE) {
        continue;
      }
    }
    used_servers = g_list_prepend(used_servers, cur_server);
  }

  return used_servers;
}

static int server_to_unbound_string(FILE *config_file, server_uri_t *server) {
  char addr_buffer[INET6_ADDRSTRLEN];
  uint16_t port;

  ip_to_str(&server->address, addr_buffer);

  fprintf(config_file, "\tforward-addr: %s", addr_buffer);
  if (server->address.ss_family == AF_INET) {
    port = ntohs(((struct sockaddr_in *)&server->address)->sin_port);
  } else {
    port = ntohs(((struct sockaddr_in6 *)&server->address)->sin6_port);
  }

  if (server->protocol == DNS_TLS) {
    if (port != 0) {
      fprintf(config_file, "@%d", port);
    } else {
      fprintf(config_file, "@853");
    }
    if (server->name) {
      fprintf(config_file, "#%s", server->name);
    }
  } else if (port != 0) {
    fprintf(config_file, "@%d", port);
  }
  fprintf(config_file, "\n");

  if (ferror(config_file))
    return -1;

  return 0;
}

static int generate_forward_zones(FILE *config_file, GHashTable *domain_to_servers,
                                  dnsconfd_mode_t mode) {
  GHashTableIter iter;
  gpointer key, value;
  GList *used_servers;
  GList *l;
  server_uri_t *server;
  unsigned char tls = 0;
  unsigned char root_present = 0;

  g_hash_table_iter_init(&iter, domain_to_servers);
  while (g_hash_table_iter_next(&iter, &key, &value)) {
    used_servers = get_used_servers(value, mode, key);
    if (!used_servers)
      continue;

    fprintf(config_file, "forward-zone:\n\tname: \"%s\"\n", (char *)key);

    if (!root_present && strcmp(key, ".") == 0)
      root_present = 1;

    for (l = (GList *)used_servers; l != NULL; l = l->next) {
      server = (server_uri_t *)l->data;
      if (server->protocol == DNS_TLS)
        tls = 1;
      if (server_to_unbound_string(config_file, server) < 0) {
        g_list_free(used_servers);
        return -1;
      }
    }
    g_list_free(used_servers);
    fprintf(config_file, "\tforward-tls-upstream: %s\n", tls ? "yes" : "no");
    tls = 0;
  }

  if (!root_present) {
    fprintf(config_file, "forward-zone:\n\tname: \".\"\n\tforward-addr: \"127.0.0.1\"\n");
  }

  if (ferror(config_file))
    return -1;
  return 0;
}

static int generate_listen_address(FILE *config_file, dnsconfd_config_t *config,
                                   const char **error_string) {
  char inet_buffer[INET6_ADDRSTRLEN];

  ip_to_str(&config->listen_address, inet_buffer);

  if (fprintf(config_file, "\tinterface: %s\n\tdo-not-query-address: 127.0.0.1/8\n", inet_buffer) <
      0) {
    *error_string = "Failed to write unbound interface configuration";
    return -1;
  }

  return 0;
}

static char *effective_ca_from_uris(GHashTable *domain_to_servers, dnsconfd_mode_t mode) {
  GHashTableIter iter;
  gpointer key, value;
  server_uri_t *cur_server;
  int highest_prio;
  GList *server_iterator;
  char *effective_ca = NULL;

  g_hash_table_iter_init(&iter, domain_to_servers);

  while (g_hash_table_iter_next(&iter, &key, &value)) {
    for (server_iterator = (GList *)value; server_iterator != NULL;
         server_iterator = server_iterator->next) {
      cur_server = (server_uri_t *)server_iterator->data;
      if (!cur_server->certification_authority)
        continue;
      // if this server can not be used globally and we are in strict mode, then
      // skip it
      if (cur_server->interface[0] != '\0') {
        if ((mode > MODE_BACKUP && strcmp(key, ".") == 0) || mode == MODE_EXCLUSIVE) {
          continue;
        }
      }
      if ((effective_ca == NULL || cur_server->priority < highest_prio) &&
          cur_server->protocol == DNS_TLS) {
        highest_prio = cur_server->priority;
        effective_ca = cur_server->certification_authority;
      }
    }
  }

  return effective_ca ? strdup(effective_ca) : effective_ca;
}

static char *effective_ca_from_config(dnsconfd_config_t *config) {
  char *effective_ca = NULL;
  char *backup_ca = NULL;
  char *duplicated_ca;
  char *result;
  duplicated_ca = backup_ca = strdup(config->certification_authority);
  if (!duplicated_ca)
    return NULL;

  while ((effective_ca = strsep(&duplicated_ca, " "))) {
    if (access(effective_ca, R_OK) == 0)
      break;
  }

  result = strdup(effective_ca);

  free(backup_ca);
  return result;
}

static char *get_effective_ca(GHashTable *domain_to_servers, dnsconfd_mode_t mode,
                              dnsconfd_config_t *config) {
  char *effective_ca = NULL;

  if (domain_to_servers) {
    effective_ca = effective_ca_from_uris(domain_to_servers, mode);
  }

  if (!effective_ca) {
    return effective_ca_from_config(config);
  }

  return effective_ca;
}

int write_configuration(fsm_context_t *ctx, const char **error_string) {
  char *effective_ca;
  FILE *config_file = fopen("/run/dnsconfd/unbound.conf", "w");

  if (!config_file) {
    *error_string = "Failed to open unbound config file";
    return -1;
  }

  fprintf(config_file, "server:\n\tmodule-config: \"%s\"\n",
          ctx->config->dnssec_enabled == CONFIG_BOOLEAN_TRUE ? "ipsecmod validator iterator"
                                                             : "ipsecmod iterator");

  if (generate_listen_address(config_file, ctx->config, error_string)) {
    goto error;
  }

  // TODO generate_trust_bundle and generate_forward_zones both walk through
  // domain_to_servers merge them so we walk the dictionary only once
  effective_ca =
      get_effective_ca(ctx->current_domain_to_servers, ctx->resolution_mode, ctx->config);
  if (!effective_ca) {
    *error_string = "Failed to determine Unbound effective CA";
    goto error;
  }
  fprintf(config_file, "\ttls-cert-bundle: %s\n", effective_ca);

  if (ctx->effective_ca) {
    free(ctx->effective_ca);
  }
  ctx->effective_ca = effective_ca;

  if (ctx->current_domain_to_servers) {
    if (generate_forward_zones(config_file, ctx->current_domain_to_servers, ctx->resolution_mode)) {
      *error_string = "Failed to generate Unbound forward zones";
      goto error;
    }
  } else {
    fprintf(config_file, "forward-zone:\n\tname: \".\"\n\tforward-addr: \"127.0.0.1\"\n");
  }

  if (ferror(config_file)) {
    *error_string = "Error encountered while writing Unbound configuration";
    goto error;
  }

  if (fclose(config_file)) {
    *error_string = "Failed to close Unbound configuration file";
    return -1;
  }

  return 0;
error:
  fclose(config_file);
  return -1;
}

static int execute_unbound_command(char **argv) {
  gint exit_status;
  gboolean success;
  GError *error = NULL;

  success = g_spawn_sync(NULL, argv, NULL, G_SPAWN_SEARCH_PATH, NULL, NULL, NULL, NULL,
                         &exit_status, &error);

  if (!success) {
    g_error_free(error);
    return -1;
  }

  return WIFEXITED(exit_status) && WEXITSTATUS(exit_status) == 0 ? 0 : -1;
}

static int remove_domain(const char *domain) {
  char *argv[5];
  argv[0] = "unbound-control";

  if (strcmp(domain, ".") != 0) {
    argv[1] = "forward_remove";
    argv[2] = "+i";
    argv[3] = (char *)domain;
    argv[4] = NULL;
  } else {
    argv[1] = "forward_add";
    argv[2] = ".";
    argv[3] = "127.0.0.1";
    argv[4] = NULL;
  }

  if (execute_unbound_command(argv) != 0) {
    return -1;
  }

  argv[1] = "flush_zone";
  argv[2] = (char *)domain;
  argv[3] = NULL;

  return execute_unbound_command(argv);
}

static int add_domain(const char *domain, GList *servers) {
  char address_buffer[INET6_ADDRSTRLEN];
  uint16_t port;
  int ret;
  server_uri_t *cur_server = (server_uri_t *)servers->data;
  int flags = (!cur_server->dnssec) | ((cur_server->protocol == DNS_TLS) << 1);
  GPtrArray *argv_array = g_ptr_array_new_with_free_func(g_free);
  char *flush_argv[] = {"unbound-control", "flush_zone", (char *)domain, NULL};

  g_ptr_array_add(argv_array, g_strdup("unbound-control"));
  g_ptr_array_add(argv_array, g_strdup("forward_add"));

  if (flags == 1) {
    g_ptr_array_add(argv_array, g_strdup("+i"));
  } else if (flags == 2) {
    g_ptr_array_add(argv_array, g_strdup("+t"));
  } else if (flags == 3) {
    g_ptr_array_add(argv_array, g_strdup("+it"));
  }

  g_ptr_array_add(argv_array, g_strdup(domain));

  for (; servers != NULL; servers = servers->next) {
    cur_server = (server_uri_t *)servers->data;
    ip_to_str(&cur_server->address, address_buffer);

    GString *server_arg = g_string_new(address_buffer);

    if (cur_server->address.ss_family == AF_INET) {
      port = ntohs(((struct sockaddr_in *)&cur_server->address)->sin_port);
    } else {
      port = ntohs(((struct sockaddr_in6 *)&cur_server->address)->sin6_port);
    }

    if (cur_server->protocol == DNS_TLS) {
      if (port != 0) {
        g_string_append_printf(server_arg, "@%d", port);
      } else {
        g_string_append_printf(server_arg, "@853");
      }
      if (cur_server->name) {
        g_string_append_printf(server_arg, "#%s", cur_server->name);
      }
    } else if (port != 0) {
      g_string_append_printf(server_arg, "@%d", port);
    }

    g_ptr_array_add(argv_array, g_string_free(server_arg, FALSE));
  }

  g_ptr_array_add(argv_array, NULL);

  ret = execute_unbound_command((char **)argv_array->pdata);
  g_ptr_array_free(argv_array, TRUE);

  if (ret != 0)
    return -1;

  return execute_unbound_command(flush_argv);
}

static int compare_addresses(struct sockaddr_storage *a, struct sockaddr_storage *b) {
  struct sockaddr_in *s4a;
  struct sockaddr_in *s4b;
  struct sockaddr_in6 *s6a;
  struct sockaddr_in6 *s6b;

  if (a->ss_family != b->ss_family)
    return 1;

  if (a->ss_family == AF_INET) {
    s4a = ((struct sockaddr_in *)a);
    s4b = ((struct sockaddr_in *)b);
    if (s4a->sin_addr.s_addr != s4b->sin_addr.s_addr || s4a->sin_port != s4b->sin_port) {
      return 1;
    }
  } else {
    s6a = ((struct sockaddr_in6 *)a);
    s6b = ((struct sockaddr_in6 *)b);
    if (s6a->sin6_port != s6b->sin6_port) {
      return 1;
    }
    if (memcmp(&s6a->sin6_addr, &s6b->sin6_addr, sizeof(struct in6_addr))) {
      return 1;
    }
  }
  return 0;
}

static int compare_servers(GList *a, GList *b) {
  server_uri_t *server_a;
  server_uri_t *server_b;

  if (g_list_length(a) != g_list_length(b)) {
    return 1;
  }

  while (a != NULL) {
    server_a = (server_uri_t *)a->data;
    server_b = (server_uri_t *)b->data;
    if (compare_addresses(&server_a->address, &server_b->address) != 0) {
      return 1;
    }
    if (server_a->priority != server_b->priority) {
      return 1;
    }
    if (strcmp(server_a->interface, server_b->interface) != 0) {
      return 1;
    }
    if (server_a->dnssec != server_b->dnssec) {
      return 1;
    }
    if (server_a->protocol != server_b->protocol) {
      return 1;
    }
    if (!server_a->certification_authority != !server_b->certification_authority) {
      return 1;
    } else if (server_a->certification_authority && server_b->certification_authority &&
               strcmp(server_a->certification_authority, server_b->certification_authority) != 0) {
      return 1;
    }
    if (!server_a->name != !server_b->name) {
      return 1;
    } else if (server_a->name && server_b->name && strcmp(server_a->name, server_b->name) != 0) {
      return 1;
    }
    // routing_domains, search_domains and networks won't be checked, as their
    // change is processed in different parts of the code
    a = a->next;
    b = b->next;
  }

  return 0;
}

static void destroy_hash_table_cloned_list(gpointer pointer) {
  g_list_free_full((GList *)pointer, server_uri_t_destroy);
}

// -1 error, 0 continue, 1 reload
int update(fsm_context_t *ctx, GHashTable **result, const char **error_string) {
  GList *used_servers;
  GList *old_servers;
  char *new_effective_ca;
  GHashTableIter iter;
  gpointer key, value;
  int ca_comparison;
  GHashTable *new_unbound_domain_to_servers = g_hash_table_new_full(
      g_str_hash, g_str_equal, g_free, (GDestroyNotify)destroy_hash_table_cloned_list);

  g_hash_table_iter_init(&iter, ctx->current_domain_to_servers);
  while (g_hash_table_iter_next(&iter, &key, &value)) {
    used_servers = get_used_servers((GList *)value, ctx->resolution_mode, key);
    if (!used_servers)
      continue;
    server_uri_t_list_replace_elements_with_copies(used_servers);
    g_hash_table_insert(new_unbound_domain_to_servers, g_strdup(key), used_servers);
  }

  // now we have new_unbound_domain_to_servers ready, check if the CA differs

  new_effective_ca =
      get_effective_ca(new_unbound_domain_to_servers, ctx->resolution_mode, ctx->config);

  if (!new_effective_ca) {
    *error_string = "Failed to determine new effective CA of Unbound";
    goto error;
  }

  ca_comparison = strcmp(new_effective_ca, ctx->effective_ca);
  free(new_effective_ca);

  if (ca_comparison != 0) {
    g_hash_table_destroy(new_unbound_domain_to_servers);
    // reload required
    return 1;
  }

  g_hash_table_iter_init(&iter, new_unbound_domain_to_servers);
  while (g_hash_table_iter_next(&iter, &key, &value)) {
    used_servers = value;
    if (ctx->current_unbound_domain_to_servers) {
      old_servers = g_hash_table_lookup(ctx->current_unbound_domain_to_servers, key);
    } else {
      old_servers = NULL;
    }
    if (old_servers && compare_servers(used_servers, old_servers) == 0) {
      // TODO compare servers is not perfect, as if you would switch 2 servers
      // with the same absolute priority, the list would from resolution
      // perspective be still equal but we would sign it is not, hashing
      // function has to be implemented
      continue;
    }
    if (add_domain((char *)key, used_servers)) {
      *error_string = "Failed to add domain to Unbound";
      goto error;
    }
  }

  if (ctx->current_unbound_domain_to_servers) {
    g_hash_table_iter_init(&iter, ctx->current_unbound_domain_to_servers);
    while (g_hash_table_iter_next(&iter, &key, &value)) {
      if (!g_hash_table_contains(new_unbound_domain_to_servers, key)) {
        if (remove_domain((char *)key) != 0) {
          goto error;
        }
      }
    }
  }

  *result = new_unbound_domain_to_servers;
  return 0;
error:
  g_hash_table_destroy(new_unbound_domain_to_servers);
  return -1;
}

int write_resolv_conf(dnsconfd_config_t *config, GHashTable *domain_to_servers, GString **backup,
                      dnsconfd_mode_t mode, const char **error_string) {
  GHashTableIter iter;
  gpointer key, value;
  GList *used_servers;
  GList *backup_servers;
  GList *cur_search;
  char *original_content = NULL;
  char inet_buffer[INET6_ADDRSTRLEN];
  int first_search = 1;
  GHashTable *searches_table;
  FILE *resolv_conf_file;

  if (!*backup) {
    if (g_file_get_contents(config->resolv_conf_path, &original_content, NULL, NULL)) {
      *backup = g_string_new(original_content);
      g_free(original_content);
    } else {
      *error_string = "Failed to create backup of resolv.conf";
      return -1;
    }
  }

  resolv_conf_file = fopen(config->resolv_conf_path, "w");
  if (!resolv_conf_file) {
    *error_string = "Failed to open resolv.conf";
    return -1;
  }

  searches_table = g_hash_table_new(g_str_hash, g_str_equal);

  fprintf(resolv_conf_file, "#Generated by dnsconfd\n");

  g_hash_table_iter_init(&iter, domain_to_servers);
  while (g_hash_table_iter_next(&iter, &key, &value)) {
    used_servers = backup_servers = get_used_servers((GList *)value, mode, key);
    if (!used_servers)
      continue;

    for (; used_servers != NULL; used_servers = used_servers->next) {
      cur_search = ((server_uri_t *)used_servers->data)->search_domains;
      for (; cur_search != NULL; cur_search = cur_search->next) {
        if (!g_hash_table_contains(searches_table, cur_search->data)) {
          fprintf(resolv_conf_file, "%s%s", first_search ? "search " : " ",
                  (char *)cur_search->data);
          first_search = 0;
          g_hash_table_insert(searches_table, cur_search->data, NULL);
        }
      }
    }
    g_list_free(backup_servers);
  }

  if (!first_search) {
    fprintf(resolv_conf_file, "\n");
  }

  g_hash_table_destroy(searches_table);

  if (config->resolver_options) {
    fprintf(resolv_conf_file, "options %s\n", config->resolver_options);
  }

  ip_to_str(&config->listen_address, inet_buffer);

  fprintf(resolv_conf_file, "nameserver %s\n", inet_buffer);

  if (ferror(resolv_conf_file)) {
    *error_string = "Error encountered while writing to resolv.conf";
    return -1;
  } else if (fclose(resolv_conf_file)) {
    *error_string = "Error encountered while closing resolv.conf";
    return -1;
  }

  return 0;
}
