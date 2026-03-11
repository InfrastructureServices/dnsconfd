#ifndef SERVICE_MANAGEMENT_H
#define SERVICE_MANAGEMENT_H

#include <gio/gio.h>
#include <glib.h>

typedef void (*service_job_completed_cb)(const char *result, gpointer user_data);

typedef struct {
  char *expected_status;
  service_job_completed_cb callback;
  gpointer user_data;
  GFileMonitor *monitor;
  gulong handler_id;
} ServiceManagementContext;

void service_management_context_destroy(ServiceManagementContext *ctx);

unsigned int set_service_status(ServiceManagementContext *ctx, char *expected_status, char *command,
                                GError **error);

int service_management_subscribe_job_removed(ServiceManagementContext *ctx,
                                             service_job_completed_cb callback, gpointer user_data);

#endif /* SERVICE_MANAGEMENT_H */
