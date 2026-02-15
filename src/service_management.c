#include "service_management.h"

#include <gio/gio.h>
#include <stdio.h>

static unsigned int call_systemd_manager(GDBusConnection *connection, const char *method,
                                         const char *service_name, GError **error) {
  GVariant *result;
  unsigned long job_id;
  char *job_string;
  char *end_ptr;

  /*
   * Call the method on the systemd Manager interface.
   * Signature for StartUnit, StopUnit, RestartUnit is (ss) -> (o)
   * Input: (service_name, mode) where mode is usually "replace"
   * Output: (job_path)
   */
  result = g_dbus_connection_call_sync(
      connection, "org.freedesktop.systemd1", "/org/freedesktop/systemd1",
      "org.freedesktop.systemd1.Manager", method, g_variant_new("(ss)", service_name, "replace"),
      G_VARIANT_TYPE("(o)"), G_DBUS_CALL_FLAGS_NONE, -1, NULL, error);

  if (!result) {
    return 0;
  }

  g_variant_get(result, "(&o)", &job_string);

  job_string = strrchr(job_string, '/');
  errno = 0;
  // systemd job ids are unsigned 32 bit integers starting at 1
  job_id = strtoul(job_string + 1, &end_ptr, 10);
  if (*end_ptr != '\0' || errno != 0) {
    g_variant_unref(result);
    errno = 0;
    return 0;
  }

  g_variant_unref(result);

  return (unsigned int)job_id;
}

unsigned int service_start(GDBusConnection *connection, const char *service_name, GError **error) {
  return call_systemd_manager(connection, "RestartUnit", service_name, error);
}

unsigned int service_stop(GDBusConnection *connection, const char *service_name, GError **error) {
  return call_systemd_manager(connection, "StopUnit", service_name, error);
}

typedef struct {
  service_job_completed_cb callback;
  gpointer user_data;
} signal_closure_t;

static void on_job_removed_signal(GDBusConnection *connection, const gchar *sender_name,
                                  const gchar *object_path, const gchar *interface_name,
                                  const gchar *signal_name, GVariant *parameters,
                                  gpointer user_data) {
  signal_closure_t *closure = (signal_closure_t *)user_data;
  guint32 id;
  const gchar *path;
  const gchar *unit;
  const gchar *result;

  /*
   * JobRemoved signal signature: (uoss)
   * u: id
   * o: path
   * s: unit
   * s: result
   */
  g_variant_get(parameters, "(u&o&s&s)", &id, &path, &unit, &result);

  if (closure && closure->callback) {
    closure->callback(id, result, closure->user_data);
  }
}

guint service_management_subscribe_job_removed(GDBusConnection *connection,
                                               service_job_completed_cb callback,
                                               gpointer user_data) {
  signal_closure_t *closure;

  if (!connection || !callback) {
    return 0;
  }

  if (!(closure = malloc(sizeof(signal_closure_t))))
    return 0;

  closure->callback = callback;
  closure->user_data = user_data;

  return g_dbus_connection_signal_subscribe(
      connection, "org.freedesktop.systemd1", "org.freedesktop.systemd1.Manager", "JobRemoved",
      "/org/freedesktop/systemd1", NULL, G_DBUS_SIGNAL_FLAGS_NONE, on_job_removed_signal, closure,
      free);
}

void service_management_unsubscribe_job_removed(GDBusConnection *connection,
                                                guint subscription_id) {
  g_dbus_connection_signal_unsubscribe(connection, subscription_id);
}
