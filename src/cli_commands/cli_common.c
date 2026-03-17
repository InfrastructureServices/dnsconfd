#include "cli_common.h"

#include <stdio.h>
#include <string.h>

#include "dnsconfd_config.h"
#include "log_utilities.h"
#include "print_utils.h"

GDBusConnection *cli_connect_to_dbus() {
  GError *error = NULL;
  GDBusConnection *connection = g_bus_get_sync(G_BUS_TYPE_SYSTEM, NULL, &error);
  if (error) {
    fprintf(stderr, "Error connecting to system bus: %s\n", error->message);
    g_error_free(error);
    return NULL;
  }
  return connection;
}

int cli_call_simple_method(GDBusConnection *connection, const char *method_name,
                           unsigned char json) {
  GError *error = NULL;
  GVariant *result;
  const gchar *response;

  result = g_dbus_connection_call_sync(
      connection, "com.redhat.dnsconfd", "/com/redhat/dnsconfd", "com.redhat.dnsconfd.Manager",
      method_name, NULL, G_VARIANT_TYPE("(s)"), G_DBUS_CALL_FLAGS_NONE, -1, NULL, &error);

  if (error) {
    fprintf(stderr, "Error calling %s method: %s\n", method_name, error->message);
    g_error_free(error);
    return EXIT_COMMAND_FAILURE;
  }

  g_variant_get(result, "(&s)", &response);
  if (strcmp(method_name, "Status") == 0)
    // If the json parsing fails for any reason, just print the raw string at least
    if (json || print_status(response))
      printf("%s\n", response);

  g_variant_unref(result);
  return EXIT_OK;
}

int cli_execute_simple_command(const char *method_name, unsigned char json) {
  int ret;
  GDBusConnection *connection = cli_connect_to_dbus();

  if (!connection)
    return EXIT_COMMAND_FAILURE;

  ret = cli_call_simple_method(connection, method_name, json);
  g_object_unref(connection);
  return ret;
}
