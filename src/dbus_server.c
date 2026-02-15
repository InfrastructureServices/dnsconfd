#include "dbus_server.h"

#include <gio/gio.h>
#include <glib-unix.h>
#include <idn2.h>
#include <jansson.h>
#include <linux/if.h>
#include <netinet/in.h>
#include <stdio.h>
#include <string.h>
#include <syslog.h>

#include "fsm/fsm.h"
#include "ip_utilities.h"
#include "log_utilities.h"
#include "types/network_address.h"
#include "types/server_uri.h"

static const gchar introspection_xml[] =
    "<node>"
    "  <interface name='com.redhat.dnsconfd.Manager'>"
    "    <method name='Update'>"
    "      <arg direction='in'  type='aa{sv}' name='servers' />"
    "      <arg direction='in'  type='u'      name='mode'    />"
    "      <arg direction='out' type='u' />"
    "      <arg direction='out' type='s' />"
    "    </method>"
    "    <method name='Status'>"
    "      <arg direction='out' type='s' />"
    "    </method>"
    "    <method name='Reload'>"
    "      <arg direction='out' type='s' />"
    "    </method>"
    "    <property name='configuration_serial' type='u' access='read'/>"
    "  </interface>"
    "</node>";
enum parse_error_code {
  PARSE_ERROR_NONE = 0,
  PARSE_ERROR_OOM = 1,
  PARSE_ERROR_MISSING_ADDRESS = 2,
  PARSE_ERROR_INVALID_ADDRESS = 3,
  PARSE_ERROR_PORT_INVALID = 4,
  PARSE_ERROR_INVALID_PROTOCOL = 5,
  PARSE_ERROR_INTERFACE_TOO_LONG = 6,
  PARSE_ERROR_INVALID_NET = 7,
  PARSE_ERROR_INVALID_DOMAIN = 8,
  PARSE_ERROR_INVALID_MODE = 9,
};

static const char *parse_error_strings[] = {
    NULL,
    "Out of memory",
    "Server does not have address set",
    "Address is not a valid IP address",
    "Port is not a valid port.",
    "Protocol is not supported",
    "Interface name can have at most 15 characters",
    "Network address is invalid",
    "Domain name is invalid",
    "Mode is invalid",
};

static int parse_address(GVariantDict *cur_server_dict, server_uri_t *cur_server) {
  gchar *cur_string;
  int parse_ok;
  gsize n_elements;
  const guchar *fixed_array;
  struct sockaddr_in *sa4 = (struct sockaddr_in *)&cur_server->address;
  struct sockaddr_in6 *sa6 = (struct sockaddr_in6 *)&cur_server->address;
  GVariant *cur_param =
      g_variant_dict_lookup_value(cur_server_dict, "address", G_VARIANT_TYPE_STRING);

  if (cur_param) {
    g_variant_get(cur_param, "&s", &cur_string);
    parse_ok = parse_ip_str(cur_string, &cur_server->address);
    g_variant_unref(cur_param);
    return parse_ok != 0 ? PARSE_ERROR_INVALID_ADDRESS : PARSE_ERROR_NONE;
  }

  cur_param = g_variant_dict_lookup_value(cur_server_dict, "address", G_VARIANT_TYPE_BYTESTRING);

  if (!cur_param)
    return PARSE_ERROR_MISSING_ADDRESS;

  fixed_array = g_variant_get_fixed_array(cur_param, &n_elements, sizeof(guchar));
  g_variant_unref(cur_param);

  memset(&cur_server->address, 0, sizeof(struct sockaddr_storage));

  if (n_elements == 4) {
    sa4->sin_family = AF_INET;
    memcpy(&sa4->sin_addr, fixed_array, 4);
  } else if (n_elements == 16) {
    sa6->sin6_family = AF_INET6;
    memcpy(&sa6->sin6_addr, fixed_array, 16);
  } else {
    return PARSE_ERROR_INVALID_ADDRESS;
  }

  return PARSE_ERROR_NONE;
}

static int parse_port(GVariant *cur_param, server_uri_t *cur_server) {
  gint32 raw_port;

  g_variant_get(cur_param, "i", &raw_port);
  if (raw_port < 0 || raw_port > 65535) {
    return PARSE_ERROR_PORT_INVALID;
  }

  if (cur_server->address.ss_family == AF_INET) {
    ((struct sockaddr_in *)&cur_server->address)->sin_port = htons((uint16_t)raw_port);
  } else {
    ((struct sockaddr_in6 *)&cur_server->address)->sin6_port = htons((uint16_t)raw_port);
  }

  return PARSE_ERROR_NONE;
}

static int parse_priority(GVariant *cur_param, server_uri_t *cur_server) {
  gint32 raw_priority;

  g_variant_get(cur_param, "i", &raw_priority);
  cur_server->priority = raw_priority;
  return PARSE_ERROR_NONE;
}

static int parse_protocol(GVariant *cur_param, server_uri_t *cur_server) {
  const gchar *protocol_str;

  g_variant_get(cur_param, "&s", &protocol_str);

  cur_server->protocol = protocol_from_nstring(protocol_str, strlen(protocol_str));

  if (cur_server->protocol == DNS_PROTOCOLS_END)
    return PARSE_ERROR_INVALID_PROTOCOL;

  return PARSE_ERROR_NONE;
}

static int parse_interface(GVariant *cur_param, server_uri_t *cur_server) {
  const gchar *interface_str;

  g_variant_get(cur_param, "&s", &interface_str);
  if (strlen(interface_str) >= IFNAMSIZ) {
    return PARSE_ERROR_INTERFACE_TOO_LONG;
  }
  strcpy(cur_server->interface, interface_str);
  return PARSE_ERROR_NONE;
}

static int parse_dnssec(GVariant *cur_param, server_uri_t *cur_server) {
  gboolean dnssec_val;
  g_variant_get(cur_param, "b", &dnssec_val);
  cur_server->dnssec = dnssec_val ? 1 : 0;

  return PARSE_ERROR_NONE;
}

static int parse_ca(GVariant *cur_param, server_uri_t *cur_server) {
  const gchar *ca_str;

  g_variant_get(cur_param, "&s", &ca_str);
  cur_server->certification_authority = strdup(ca_str);
  if (!cur_server->certification_authority)
    return PARSE_ERROR_OOM;

  return PARSE_ERROR_NONE;
}

static int parse_name(GVariant *cur_param, server_uri_t *cur_server) {
  const gchar *name_str;

  g_variant_get(cur_param, "&s", &name_str);
  cur_server->name = strdup(name_str);
  if (!cur_server->name)
    return PARSE_ERROR_OOM;

  return PARSE_ERROR_NONE;
}

static int save_domains(GVariant *cur_param, GList **where) {
  GVariantIter iter;
  gchar *domain_str;
  uint8_t *domain_idn;

  g_variant_iter_init(&iter, cur_param);
  while (g_variant_iter_next(&iter, "&s", &domain_str)) {
    if (strstr(domain_str, "..") ||
        idn2_lookup_u8((uint8_t *)domain_str, &domain_idn, IDN2_NFC_INPUT) != IDN2_OK) {
      return PARSE_ERROR_INVALID_DOMAIN;
    }

    *where = g_list_append(*where, (char *)domain_idn);
  }

  return PARSE_ERROR_NONE;
}

static int parse_domains(GVariant *cur_param, server_uri_t *cur_server) {
  return save_domains(cur_param, &cur_server->routing_domains);
}

static int parse_search(GVariant *cur_param, server_uri_t *cur_server) {
  return save_domains(cur_param, &cur_server->search_domains);
}

static int parse_networks(GVariant *cur_param, server_uri_t *cur_server) {
  GVariantIter iter;
  gchar *network_str;
  network_address_t *net;

  g_variant_iter_init(&iter, cur_param);
  while (g_variant_iter_next(&iter, "&s", &network_str)) {
    if (!(net = malloc(sizeof(network_address_t))))
      return PARSE_ERROR_OOM;

    if (network_address_t_from_string(network_str, net) != 0) {
      free(net);
      return PARSE_ERROR_INVALID_NET;
    }
    cur_server->networks = g_list_append(cur_server->networks, net);
  }
  return PARSE_ERROR_NONE;
}

static GVariant *handle_update_call(GVariant *parameters, fsm_context_t *ctx) {
  guint32 mode;
  GVariant *cur_server_params;
  GVariant *result;
  GVariantIter *servers_iter;
  GVariantDict cur_server_dict;
  char *domain_dup;
  server_uri_t *cur_server = NULL;
  GVariant *cur_param = NULL;
  GList *parsed_servers = NULL;
  int parse_error = PARSE_ERROR_NONE;
  int field_error = 0;

  dnsconfd_log(LOG_DEBUG, ctx->config, "Handling Update call");

  struct {
    const char *key;
    const GVariantType *type;
    int (*parser)(GVariant *, server_uri_t *);
  } key_type_parser[] = {{"port", G_VARIANT_TYPE_INT32, parse_port},
                         {"priority", G_VARIANT_TYPE_INT32, parse_priority},
                         {"protocol", G_VARIANT_TYPE_STRING, parse_protocol},
                         {"interface", G_VARIANT_TYPE_STRING, parse_interface},
                         {"dnssec", G_VARIANT_TYPE_BOOLEAN, parse_dnssec},
                         {"ca", G_VARIANT_TYPE_STRING, parse_ca},
                         {"name", G_VARIANT_TYPE_STRING, parse_name},
                         {"routing_domains", G_VARIANT_TYPE_STRING_ARRAY, parse_domains},
                         {"search_domains", G_VARIANT_TYPE_STRING_ARRAY, parse_search},
                         {"networks", G_VARIANT_TYPE_STRING_ARRAY, parse_networks}};

  g_variant_get(parameters, "(aa{sv}u)", &servers_iter, &mode);
  dnsconfd_log(LOG_DEBUG, ctx->config, "Update mode: %u", mode);

  if (mode < 0 || mode > 2) {
    parse_error = PARSE_ERROR_INVALID_MODE;
    result = g_variant_new("(us)", 0, parse_error_strings[parse_error]);
  }

  while (parse_error == PARSE_ERROR_NONE &&
         g_variant_iter_loop(servers_iter, "@a{sv}", &cur_server_params)) {
    cur_server = malloc(sizeof(server_uri_t));
    if (!cur_server) {
      parse_error = PARSE_ERROR_OOM;
      result = g_variant_new("(us)", 0, parse_error_strings[PARSE_ERROR_OOM]);
      break;
    }
    *cur_server = (server_uri_t){.dnssec = 1};
    g_variant_dict_init(&cur_server_dict, cur_server_params);
    if ((parse_error = parse_address(&cur_server_dict, cur_server)) != PARSE_ERROR_NONE) {
      server_uri_t_destroy(cur_server);
      g_variant_dict_clear(&cur_server_dict);
      result = g_variant_new("(us)", 0, parse_error_strings[parse_error]);
      break;
    }

    for (size_t i = 0; i < sizeof(key_type_parser) / sizeof(key_type_parser[0]); i++) {
      cur_param = g_variant_dict_lookup_value(&cur_server_dict, key_type_parser[i].key,
                                              key_type_parser[i].type);

      if (cur_param) {
        parse_error = key_type_parser[i].parser(cur_param, cur_server);
        g_variant_unref(cur_param);
        if (parse_error != PARSE_ERROR_NONE) {
          field_error = 1;
          result = g_variant_new("(us)", 0, parse_error_strings[parse_error]);
          break;
        }
      }
    }
    if (field_error) {
      server_uri_t_destroy(cur_server);
      g_variant_dict_clear(&cur_server_dict);
      break;
    }

    if (!cur_server->routing_domains) {
      domain_dup = strdup(".");
      if (!domain_dup) {
        server_uri_t_destroy(cur_server);
        g_variant_dict_clear(&cur_server_dict);
        parse_error = PARSE_ERROR_OOM;
        result = g_variant_new("(us)", 0, parse_error_strings[PARSE_ERROR_OOM]);
        break;
      }
      cur_server->routing_domains = g_list_append(NULL, domain_dup);
    }

    set_default_port(&cur_server->address, cur_server->protocol != DNS_TLS ? 53 : 853);

    gboolean duplicate = FALSE;
    for (GList *l = parsed_servers; l != NULL; l = l->next) {
      server_uri_t *existing = (server_uri_t *)l->data;
      if (are_ips_equal(&cur_server->address, &existing->address)) {
        if (g_strcmp0(cur_server->interface, existing->interface) != 0) {
          char addr_str[INET6_ADDRSTRLEN];
          ip_to_str(&cur_server->address, addr_str);
          dnsconfd_log(LOG_NOTICE, ctx->config,
                       "Ignoring server %s on interface %s because it is "
                       "already present on "
                       "interface %s",
                       addr_str, cur_server->interface, existing->interface);
          duplicate = TRUE;
          break;
        }
      }
    }

    g_variant_dict_clear(&cur_server_dict);

    if (duplicate) {
      server_uri_t_destroy(cur_server);
      dnsconfd_log(LOG_DEBUG, ctx->config, "Skipping duplicate server");
      continue;
    }

    parsed_servers = g_list_append(parsed_servers, cur_server);
    dnsconfd_log(LOG_DEBUG, ctx->config, "Parsed server successfully");
  }

  if (parse_error != PARSE_ERROR_NONE) {
    dnsconfd_log(LOG_DEBUG, ctx->config, "Update failed with error: %s",
                 parse_error_strings[parse_error]);
    g_list_free_full(parsed_servers, server_uri_t_destroy);
  } else {
    ctx->new_dynamic_servers = parsed_servers;
    ctx->resolution_mode = mode;
    if (state_transition(ctx, EVENT_UPDATE)) {
      dnsconfd_log(LOG_ERR, ctx->config,
                   "Update resulted in unexpected state of FSM, please report "
                   "bug. Will immediately "
                   "stop to prevent any damage");
      ctx->exit_code = EXIT_FSM_FAILURE;
      g_main_loop_quit(ctx->main_loop);
    }
    dnsconfd_log(LOG_DEBUG, ctx->config, "Update accepted and state transition initiated");
    result = g_variant_new("(us)", ctx->requested_configuration_serial, "Update accepted");
  }

  g_variant_iter_free(servers_iter);
  return result;
}

static json_t *construct_cache_config_status(GHashTable *current_unbound_domain_to_servers) {
  GHashTableIter iter;
  gpointer key, value;
  json_t *new_object;
  json_t *servers_arr;
  server_uri_t *cur_server;
  char addr_str[INET6_ADDRSTRLEN];
  uint16_t port;
  GString *uri_str = g_string_new_len(NULL, 128);

  // Cache config
  new_object = json_object();
  if (current_unbound_domain_to_servers) {
    g_hash_table_iter_init(&iter, current_unbound_domain_to_servers);
    while (g_hash_table_iter_next(&iter, &key, &value)) {
      servers_arr = json_array();
      for (GList *l = (GList *)value; l != NULL; l = l->next) {
        cur_server = (server_uri_t *)l->data;
        ip_to_str(&cur_server->address, addr_str);

        if (cur_server->address.ss_family == AF_INET) {
          port = ntohs(((struct sockaddr_in *)&cur_server->address)->sin_port);
        } else {
          port = ntohs(((struct sockaddr_in6 *)&cur_server->address)->sin6_port);
        }

        if (cur_server->address.ss_family == AF_INET) {
          g_string_printf(uri_str, "%s://%s", dns_protocol_t_to_string(cur_server->protocol),
                          addr_str);
        } else {
          g_string_printf(uri_str, "%s://[%s]", dns_protocol_t_to_string(cur_server->protocol),
                          addr_str);
        }

        if (cur_server->protocol == DNS_TLS) {
          if (port != 853) {
            g_string_append_printf(uri_str, ":%d", port);
          }
          if (cur_server->name) {
            g_string_append_printf(uri_str, "#%s", cur_server->name);
          }
        } else {
          if (port != 53) {
            g_string_append_printf(uri_str, ":%d", port);
          }
        }

        json_array_append_new(servers_arr, json_string(uri_str->str));
      }
      json_object_set_new(new_object, (char *)key, servers_arr);
    }
  }

  g_string_free(uri_str, 1);
  return new_object;
}

static json_t *config_to_json(fsm_context_t *ctx) {
  json_t *root = json_object();
  json_t *servers_array = json_array();

  // Service
  json_object_set_new(root, "service", json_string("unbound"));

  // Mode
  json_object_set_new(root, "mode", json_string(dnsconfd_mode_t_to_string(ctx->resolution_mode)));

  json_object_set_new(root, "cache_config",
                      construct_cache_config_status(ctx->current_unbound_domain_to_servers));

  json_object_set_new(root, "state", json_string(fsm_state_t_to_string(ctx->current_state)));

  // Servers
  for (GList *l = ctx->all_servers; l != NULL; l = l->next) {
    json_array_append_new(servers_array, server_uri_to_json((server_uri_t *)l->data));
  }
  json_object_set_new(root, "servers", servers_array);

  return root;
}

static GVariant *handle_status_call(fsm_context_t *ctx) {
  json_t *root = config_to_json(ctx);
  char *json_str = json_dumps(root, 0);
  GVariant *result = g_variant_new("(s)", json_str);
  free(json_str);
  json_decref(root);
  return result;
}

static GVariant *handle_reload_call(fsm_context_t *ctx) {
  if (state_transition(ctx, EVENT_RELOAD)) {
    dnsconfd_log(LOG_ERR, ctx->config,
                 "Reload resulted in unexpected state of FSM, please report "
                 "bug. Will immediately "
                 "stop to prevent any damage");
    ctx->exit_code = EXIT_FSM_FAILURE;
    g_main_loop_quit(ctx->main_loop);
  }

  return g_variant_new("(s)", "Reload accepted");
}

static GVariant *handle_get_property(GDBusConnection *connection, const gchar *sender,
                                     const gchar *object_path, const gchar *interface_name,
                                     const gchar *property_name, GError **error,
                                     gpointer user_data) {
  fsm_context_t *ctx = (fsm_context_t *)user_data;
  GVariant *ret = NULL;

  if (g_strcmp0(property_name, "configuration_serial") == 0) {
    ret = g_variant_new_uint32(ctx->current_configuration_serial);
  }

  return ret;
}

static void handle_method_call(GDBusConnection *connection, const gchar *sender,
                               const gchar *object_path, const gchar *interface_name,
                               const gchar *method_name, GVariant *parameters,
                               GDBusMethodInvocation *invocation, gpointer user_data) {
  fsm_context_t *ctx = (fsm_context_t *)user_data;

  if (g_strcmp0(method_name, "Update") == 0) {
    GVariant *result = handle_update_call(parameters, ctx);
    g_dbus_method_invocation_return_value(invocation, result);
  } else if (g_strcmp0(method_name, "Status") == 0) {
    GVariant *result = handle_status_call(ctx);
    g_dbus_method_invocation_return_value(invocation, result);
  } else if (g_strcmp0(method_name, "Reload") == 0) {
    GVariant *result = handle_reload_call(ctx);
    g_dbus_method_invocation_return_value(invocation, result);
  } else {
    // Handle unknown methods (good practice, though improbable with
    // introspection)
    g_dbus_method_invocation_return_error(invocation, G_IO_ERROR, G_IO_ERROR_NOT_SUPPORTED,
                                          "Method %s not implemented", method_name);
  }
}

/* --- VTable ---
 * This table tells GDBus which functions to call for this object.
 */
static const GDBusInterfaceVTable interface_vtable = {
    handle_method_call,
    handle_get_property, // get_property
    NULL                 // set_property
};

/* --- Bus Lifecycle Callbacks --- */

static void on_bus_acquired(GDBusConnection *connection, const gchar *name, gpointer user_data) {
  guint registration_id;
  fsm_context_t *ctx = user_data;

  ctx->dbus_connection = connection;
  // Parse the XML data
  ctx->introspection_data = g_dbus_node_info_new_for_xml(introspection_xml, NULL);

  // Register the object
  // We register the FIRST interface defined in the XML node info
  registration_id = g_dbus_connection_register_object(
      connection, "/com/redhat/dnsconfd", ctx->introspection_data->interfaces[0], &interface_vtable,
      user_data, // user_data
      NULL,      // user_data_free_func
      NULL       // GError
  );

  dnsconfd_log(LOG_NOTICE, ((fsm_context_t *)user_data)->config,
               "Bus acquired, object registered at /com/redhat/dnsconfd (ID: %u)\n",
               registration_id);
}

static void on_name_acquired(GDBusConnection *connection, const gchar *name, gpointer user_data) {
  fsm_context_t *ctx = (fsm_context_t *)user_data;
  dnsconfd_log(LOG_NOTICE, ctx->config, "Acquired the name %s\n", name);

  if (state_transition(ctx, EVENT_KICKOFF)) {
    dnsconfd_log(LOG_ERR, ctx->config,
                 "Start resulted in unexpected state of FSM, please report "
                 "bug. Will immediately "
                 "stop to prevent any damage");
    ctx->exit_code = EXIT_FSM_FAILURE;
    g_main_loop_quit(ctx->main_loop);
  }
}

static void on_name_lost(GDBusConnection *connection, const gchar *name, gpointer user_data) {
  fsm_context_t *ctx = (fsm_context_t *)user_data;
  dnsconfd_log(LOG_ERR, ctx->config, "Lost the name %s\n", name);
  ctx->exit_code = EXIT_DBUS_FAILURE;
  g_main_loop_quit(ctx->main_loop);
}

static void clean_context(fsm_context_t *ctx) {
  if (ctx->current_dynamic_servers) {
    g_list_free_full(ctx->current_dynamic_servers, server_uri_t_destroy);
  }
  if (ctx->new_dynamic_servers) {
    g_list_free_full(ctx->new_dynamic_servers, server_uri_t_destroy);
  }
  if (ctx->all_servers) {
    g_list_free(ctx->all_servers);
  }
  if (ctx->current_domain_to_servers) {
    g_hash_table_destroy(ctx->current_domain_to_servers);
  }
  if (ctx->current_unbound_domain_to_servers) {
    g_hash_table_destroy(ctx->current_unbound_domain_to_servers);
  }
  if (ctx->dbus_connection) {
    g_dbus_connection_close_sync(ctx->dbus_connection, NULL, NULL);
  }
  if (ctx->introspection_data) {
    g_dbus_node_info_unref(ctx->introspection_data);
  }
  if (ctx->main_loop) {
    g_main_loop_unref(ctx->main_loop);
  }
  if (ctx->resolv_conf_backup) {
    g_string_free(ctx->resolv_conf_backup, 1);
  }
  if (ctx->effective_ca) {
    free(ctx->effective_ca);
  }
}

static gboolean on_sigterm(gpointer user_data) {
  fsm_context_t *ctx = (fsm_context_t *)user_data;
  if (state_transition(ctx, EVENT_STOP)) {
    dnsconfd_log(LOG_ERR, ctx->config,
                 "Stop resulted in unexpected state of FSM, please report bug. "
                 "Will immediately "
                 "stop to prevent any damage");
    ctx->exit_code = EXIT_FSM_FAILURE;
    g_main_loop_quit(ctx->main_loop);
  }
  return G_SOURCE_REMOVE;
}

int dbus_server_run(dnsconfd_config_t *config) {
  GMainLoop *loop;
  guint owner_id;
  fsm_context_t ctx;

  owner_id =
      g_bus_own_name(G_BUS_TYPE_SYSTEM, "com.redhat.dnsconfd", G_BUS_NAME_OWNER_FLAGS_DO_NOT_QUEUE,
                     on_bus_acquired, on_name_acquired, on_name_lost, &ctx, NULL);

  loop = g_main_loop_new(NULL, FALSE);

  ctx = (fsm_context_t){.config = config,
                        .main_loop = loop,
                        .requested_configuration_serial = 1,
                        .current_configuration_serial = 1};

  g_unix_signal_add(SIGTERM, on_sigterm, &ctx);

  g_main_loop_run(loop);

  clean_context(&ctx);

  g_bus_unown_name(owner_id);

  return ctx.exit_code;
}
