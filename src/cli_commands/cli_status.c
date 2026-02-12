#include "cli_status.h"

#include <gio/gio.h>
#include <stdio.h>

#include "log_utilities.h"

int cli_status_command(dnsconfd_config_t* config) {
  GDBusConnection* connection;
  GError* error = NULL;
  GVariant* result;
  const gchar* status_json;

  connection = g_bus_get_sync(G_BUS_TYPE_SYSTEM, NULL, &error);
  if (error) {
    fprintf(stderr, "Error connecting to system bus: %s\n", error->message);
    g_error_free(error);
    return EXIT_COMMAND_FAILURE;
  }

  result = g_dbus_connection_call_sync(
      connection, "com.redhat.dnsconfd", "/com/redhat/dnsconfd",
      "com.redhat.dnsconfd.Manager", "Status", NULL, G_VARIANT_TYPE("(s)"),
      G_DBUS_CALL_FLAGS_NONE, -1, NULL, &error);

  if (error) {
    fprintf(stderr, "Error calling Status method: %s\n", error->message);
    g_error_free(error);
    g_object_unref(connection);
    return EXIT_COMMAND_FAILURE;
  }

  g_variant_get(result, "(&s)", &status_json);
  printf("%s\n", status_json);

  g_variant_unref(result);
  g_object_unref(connection);

  return EXIT_OK;
}
