#include "cli_update.h"

#include <arpa/inet.h>
#include <gio/gio.h>
#include <netinet/in.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "cli_common.h"
#include "ip_utilities.h"
#include "types/network_address.h"
#include "types/server_uri.h"

typedef struct {
  guint32 expected_serial;
  GMainLoop* loop;
  gboolean success;
} UpdateContext;

static void on_properties_changed(GDBusConnection* connection, const gchar* sender_name,
                                  const gchar* object_path, const gchar* interface_name,
                                  const gchar* signal_name, GVariant* parameters,
                                  gpointer user_data) {
  UpdateContext* ctx = (UpdateContext*)user_data;
  const gchar* interface;
  GVariant* changed_properties;
  GVariantIter iter;
  const gchar* key;
  GVariant* value;

  g_variant_get(parameters, "(&sa{sv}*)", &interface, &changed_properties);

  if (g_strcmp0(interface, "com.redhat.dnsconfd.Manager") != 0) return;

  g_variant_iter_init(&iter, changed_properties);
  while (g_variant_iter_next(&iter, "{&sv}", &key, &value)) {
    if (g_strcmp0(key, "configuration_serial") == 0) {
      if (g_variant_get_uint32(value) == ctx->expected_serial) {
        ctx->success = 1;
        g_main_loop_quit(ctx->loop);
      }
    }
    g_variant_unref(value);
  }
}

static gboolean on_timeout(gpointer user_data) {
  g_main_loop_quit(((UpdateContext*)user_data)->loop);
  return G_SOURCE_REMOVE;
}

static void network_address_to_string(network_address_t* net, char* buffer, size_t size) {
  char ip_str[INET6_ADDRSTRLEN];

  ip_to_str(&net->address, ip_str);

  snprintf(buffer, size, "%s/%d", ip_str, net->prefix);
}

static void build_string_array(GVariantBuilder* server_dict_builder, GList* list, char* dict_key) {
  GVariantBuilder domains_builder;
  g_variant_builder_init(&domains_builder, G_VARIANT_TYPE("as"));
  for (; list != NULL; list = list->next) {
    g_variant_builder_add(&domains_builder, "s", (char*)list->data);
  }
  g_variant_builder_add(server_dict_builder, "{sv}", dict_key,
                        g_variant_builder_end(&domains_builder));
}

static void build_networks_array(server_uri_t *server, GVariantBuilder* server_dict_builder) {
  GVariantBuilder networks_builder;
  char net_str[INET6_ADDRSTRLEN + 5];  // +5 for /128

  g_variant_builder_init(&networks_builder, G_VARIANT_TYPE("as"));
  for (GList* n = server->networks; n != NULL; n = n->next) {
    network_address_to_string((network_address_t*)n->data, net_str, sizeof(net_str));
    g_variant_builder_add(&networks_builder, "s", net_str);
  }
  g_variant_builder_add(server_dict_builder, "{sv}", "networks",
                        g_variant_builder_end(&networks_builder));
}

static void build_servers_variant(GList* servers, GVariantBuilder* servers_builder) {
  GVariantBuilder server_dict_builder;
  char addr_str[INET6_ADDRSTRLEN];
  const char* proto_str;
  server_uri_t* server;
  in_port_t port = 0;

  g_variant_builder_init(servers_builder, G_VARIANT_TYPE("aa{sv}"));

  for (; servers != NULL; servers = servers->next) {
    server = (server_uri_t*)servers->data;
    g_variant_builder_init(&server_dict_builder, G_VARIANT_TYPE("a{sv}"));

    if (server->address.ss_family == AF_INET) {
      port = ntohs(((struct sockaddr_in*)&server->address)->sin_port);
    } else {
      port = ntohs(((struct sockaddr_in6*)&server->address)->sin6_port);
    }

    ip_to_str(&server->address, addr_str);
    g_variant_builder_add(&server_dict_builder, "{sv}", "address", g_variant_new_string(addr_str));

    // Port
    if (port > 0) {
      g_variant_builder_add(&server_dict_builder, "{sv}", "port", g_variant_new_int32(port));
    }

    // Priority
    g_variant_builder_add(&server_dict_builder, "{sv}", "priority",
                          g_variant_new_int32(server->priority));

    // Protocol
    proto_str = dns_protocol_t_to_string(server->protocol);
    g_variant_builder_add(&server_dict_builder, "{sv}", "protocol",
                          g_variant_new_string(proto_str));

    // Interface
    if (strlen(server->interface) > 0) {
      g_variant_builder_add(&server_dict_builder, "{sv}", "interface",
                            g_variant_new_string(server->interface));
    }

    // DNSSEC
    g_variant_builder_add(&server_dict_builder, "{sv}", "dnssec",
                          g_variant_new_boolean(server->dnssec));

    // CA
    if (server->certification_authority) {
      g_variant_builder_add(&server_dict_builder, "{sv}", "ca",
                            g_variant_new_string(server->certification_authority));
    }

    // Name
    if (server->name) {
      g_variant_builder_add(&server_dict_builder, "{sv}", "name",
                            g_variant_new_string(server->name));
    }

    // Domains
    if (server->routing_domains) {
      build_string_array(&server_dict_builder, server->routing_domains, "routing_domains");
    }

    // Search domains
    if (server->search_domains) {
      build_string_array(&server_dict_builder, server->search_domains, "search_domains");
    }

    // Networks
    if (server->networks) {
      build_networks_array(server, &server_dict_builder);
    }

    g_variant_builder_add(servers_builder, "a{sv}", &server_dict_builder);
  }
}

static void wait_for_serial(guint32 serial, GDBusConnection* connection, UpdateContext* ctx) {
  GVariant* v;
  guint32 retrieved_serial;
  // Check if we already have the correct serial
  GVariant* prop_result = g_dbus_connection_call_sync(
      connection, "com.redhat.dnsconfd", "/com/redhat/dnsconfd", "org.freedesktop.DBus.Properties",
      "Get", g_variant_new("(ss)", "com.redhat.dnsconfd.Manager", "configuration_serial"),
      G_VARIANT_TYPE("(v)"), G_DBUS_CALL_FLAGS_NONE, -1, NULL, NULL);

  if (prop_result) {
    g_variant_get(prop_result, "(v)", &v);
    g_variant_unref(prop_result);
    retrieved_serial = g_variant_get_uint32(v);
    g_variant_unref(v);

    if (retrieved_serial == serial) {
      ctx->success = 1;
      return;
    }
  }

  // Wait for signal
  ctx->expected_serial = serial;
  ctx->loop = g_main_loop_new(NULL, FALSE);

  g_timeout_add_seconds(5, on_timeout, ctx);
  g_main_loop_run(ctx->loop);

  if (!ctx->success) {
    fprintf(stderr, "Timeout waiting for configuration update\n");
  }

  g_main_loop_unref(ctx->loop);
}

int cli_update_command(dnsconfd_config_t* config) {
  GDBusConnection* connection;
  GVariant* result;
  gchar* msg;
  GVariantBuilder servers_builder;
  guint subscription_id;
  guint32 serial;
  UpdateContext ctx = {0};
  GError* error = NULL;

  connection = cli_connect_to_dbus();
  if (!connection) return EXIT_COMMAND_FAILURE;

  // Subscribe to PropertiesChanged signal
  subscription_id = g_dbus_connection_signal_subscribe(
      connection, "com.redhat.dnsconfd", "org.freedesktop.DBus.Properties", "PropertiesChanged",
      "/com/redhat/dnsconfd", NULL, G_DBUS_SIGNAL_FLAGS_NONE, on_properties_changed, &ctx, NULL);

  build_servers_variant(config->command_options.update_options.servers_uris, &servers_builder);

  result = g_dbus_connection_call_sync(
      connection, "com.redhat.dnsconfd", "/com/redhat/dnsconfd", "com.redhat.dnsconfd.Manager",
      "Update",
      g_variant_new("(aa{sv}u)", &servers_builder, config->command_options.update_options.mode),
      G_VARIANT_TYPE("(us)"), G_DBUS_CALL_FLAGS_NONE, -1, NULL, &error);

  if (error != NULL) {
    fprintf(stderr, "Error calling Update method: %s\n", error->message);
    g_error_free(error);
    goto finish;
  }

  g_variant_get(result, "(us)", &serial, &msg);

  printf("%s (Serial: %u)\n", msg, serial);

  g_variant_unref(result);

  if (serial == 0) {
    goto finish;
  }

  wait_for_serial(serial, connection, &ctx);

finish:
  g_dbus_connection_signal_unsubscribe(connection, subscription_id);
  g_object_unref(connection);
  return ctx.success ? EXIT_OK : EXIT_COMMAND_FAILURE;
}
