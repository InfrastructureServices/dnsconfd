#include "cli_reload.h"

#include <gio/gio.h>

#include "cli_common.h"

int cli_reload_command(dnsconfd_config_t *config) {
  GDBusConnection *connection;
  GVariant *result;

  connection = cli_connect_to_dbus();
  if (!connection)
    return EXIT_COMMAND_FAILURE;

  result = cli_call_simple_method(connection, "Reload");

  if (result == NULL)
    return EXIT_COMMAND_FAILURE;

  g_variant_unref(result);
  return EXIT_OK;
}
