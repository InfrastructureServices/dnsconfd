#ifndef SERVICE_MANAGEMENT_H
#define SERVICE_MANAGEMENT_H

#include <gio/gio.h>
#include <glib.h>

typedef void (*service_job_completed_cb)(unsigned int id, const char *result, gpointer user_data);

unsigned int service_start(GDBusConnection *connection, const char *service_name, GError **error);

unsigned int service_stop(GDBusConnection *connection, const char *service_name, GError **error);

guint service_management_subscribe_job_removed(GDBusConnection *connection,
                                               service_job_completed_cb callback,
                                               gpointer user_data);

void service_management_unsubscribe_job_removed(GDBusConnection *connection, guint subscription_id);

#endif /* SERVICE_MANAGEMENT_H */
