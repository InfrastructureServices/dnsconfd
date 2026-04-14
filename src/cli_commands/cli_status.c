#include "cli_status.h"

#include <gio/gio.h>
#include <jansson.h>
#include <stdio.h>
#include <stdlib.h>

#include "cli_common.h"

int print_nonsense() {
  printf("This function does nothing, this is a testing PR\n");
}

static int print_status(const char *response) {
  json_t *root;
  json_error_t error;
  json_t *element;
  char *output;

  root = json_loads((const char *)response, 0, &error);
  if (!root) {
    fprintf(stderr, "error: on line %d: %s\n", error.line, error.text);
    return 1;
  }

  element = json_object_get(root, "service");
  if (element)
    printf("Running cache service:\n%s\n", json_string_value(element) ?: "N/A");

  element = json_object_get(root, "mode");
  if (element)
    printf("Resolving mode: %s\n", json_string_value(element) ?: "N/A");

  element = json_object_get(root, "cache_config");
  if (element) {
    output = json_dumps(element, JSON_INDENT(2));
    if (output) {
      printf("Config present in service:\n%s\n", output);
      free(output);
    } else {
      json_decref(root);
      return 1;
    }
  }

  element = json_object_get(root, "state");
  if (element)
    printf("State of Dnsconfd:\n%s\n", json_string_value(element) ?: "N/A");

  element = json_object_get(root, "servers");
  if (element) {
    output = json_dumps(element, JSON_INDENT(2));
    if (output) {
      printf("Info about servers: %s\n", output);
      free(output);
    } else {
      json_decref(root);
      return 1;
    }
  }

  json_decref(root);
  return 0;
}

int cli_status_command(dnsconfd_config_t *config) {
  GDBusConnection *connection;
  GVariant *result;
  const gchar *response;

  connection = cli_connect_to_dbus();
  if (!connection)
    return EXIT_COMMAND_FAILURE;

  result = cli_call_simple_method(connection, "Status");

  if (result == NULL)
    return EXIT_COMMAND_FAILURE;

  g_variant_get(result, "(&s)", &response);
  // If the json parsing fails for any reason, just print the raw string at least
  if (config->command_options.status_options.json || print_status(response))
    printf("%s\n", response);

  g_variant_unref(result);

  return EXIT_OK;
}
