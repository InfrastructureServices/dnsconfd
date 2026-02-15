#include "dbus-handling.h"

#include <stdio.h>

GVariantDict *get_glob_dict() {
  GError *connection_error = NULL;
  GError *proxy_error = NULL;
  GError *call_error = NULL;
  GVariant *result_unwrapped;
  GDBusConnection *connection;
  GDBusProxy *proxy;
  GVariant *result;
  GVariantDict *glob_dict;

  connection = g_bus_get_sync(G_BUS_TYPE_SYSTEM, NULL, &connection_error);
  if (connection_error) {
    g_error_free(connection_error);
    fprintf(stderr, "Could not connect to system DBus\n");
    return NULL;
  }

  proxy = g_dbus_proxy_new_sync(connection, G_DBUS_PROXY_FLAGS_NONE, NULL,
                                "org.freedesktop.NetworkManager", "/org/freedesktop/NetworkManager",
                                "org.freedesktop.DBus.Properties", NULL, &proxy_error);
  if (proxy_error) {
    g_error_free(proxy_error);
    fprintf(stderr, "Could not connect to NetworkManager\n");
    g_dbus_connection_close_sync(connection, NULL, NULL);
    g_object_unref(connection);
    return NULL;
  }

  result = g_dbus_proxy_call_sync(
      proxy, "Get",
      g_variant_new("(ss)", "org.freedesktop.NetworkManager", "GlobalDnsConfiguration"),
      G_DBUS_CALL_FLAGS_NONE, 5000, NULL, &call_error);
  g_object_unref(proxy);
  g_dbus_connection_close_sync(connection, NULL, &connection_error);
  g_object_unref(connection);

  if (call_error) {
    g_error_free(call_error);
    fprintf(stderr, "Was not able to retrieve global DNS config\n");
  }
  if (connection_error) {
    g_error_free(connection_error);
    fprintf(stderr, "Was not able to close DBus connection\n");
  }

  if (call_error || connection_error) {
    return NULL;
  }

  g_variant_get(result, "(v)", &result_unwrapped);

  g_variant_unref(result);

  glob_dict = g_variant_dict_new(result_unwrapped);
  g_variant_unref(result_unwrapped);

  if (glob_dict == NULL) {
    fprintf(stderr, "Out of memory\n");
  }
  return glob_dict;
}
