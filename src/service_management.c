#include "service_management.h"

#include "log_utilities.h"
#include <errno.h>
#include <gio/gio.h>
#include <stdio.h>
#include <string.h>
#include <syslog.h>

#define CONTROL_FILE "/run/dnsconfd/unbound_control"
#define STATUS_FILE "/run/dnsconfd/unbound_status"

static gboolean write_to_file(const char *filename, const char *content, GError **error) {
  int errsv;
  FILE *f = fopen(filename, "w");

  if (f == NULL) {
    errsv = errno;
    g_set_error(error, G_FILE_ERROR, g_file_error_from_errno(errsv), "Failed to open file '%s': %s",
                filename, g_strerror(errsv));
    return FALSE;
  } else if (fputs(content, f) == EOF) {
    errsv = errno;
    g_set_error(error, G_FILE_ERROR, g_file_error_from_errno(errsv),
                "Failed to write to file '%s': %s", filename, g_strerror(errsv));
    fclose(f);
    return FALSE;
  } else if (fclose(f) != 0) {
    errsv = errno;
    g_set_error(error, G_FILE_ERROR, g_file_error_from_errno(errsv),
                "Failed to close file '%s': %s", filename, g_strerror(errsv));
    return FALSE;
  }

  return TRUE;
}

void service_management_context_destroy(ServiceManagementContext *ctx) {
  if (ctx->monitor) {
    if (ctx->handler_id) {
      g_signal_handler_disconnect(ctx->monitor, ctx->handler_id);
    }
    g_file_monitor_cancel(ctx->monitor);
    g_object_unref(ctx->monitor);
  }
}

unsigned int set_service_status(ServiceManagementContext *ctx, char *expected_status, char *command,
                                GError **error) {
  ctx->expected_status = expected_status;
  dnsconfd_log(LOG_DEBUG, "Writing pending to status file");
  if (!write_to_file(STATUS_FILE, "pending", error)) {
    return 1;
  }

  dnsconfd_log(LOG_DEBUG, "Writing %s to control file", command);
  return write_to_file(CONTROL_FILE, command, error) ? 0 : 1;
}

static void on_file_changed(GFileMonitor *monitor, GFile *file, GFile *other_file,
                            GFileMonitorEvent event_type, gpointer user_data) {
  const char *result;
  char *content;
  ServiceManagementContext *ctx = (ServiceManagementContext *)user_data;

  if (event_type == G_FILE_MONITOR_EVENT_CHANGES_DONE_HINT ||
      event_type == G_FILE_MONITOR_EVENT_CREATED) {

    if (g_file_get_contents(STATUS_FILE, &content, NULL, NULL)) {
      g_strstrip(content);

      dnsconfd_log(LOG_DEBUG, "status file content changed %s", content);
      // possible values: pending, ready, fail, stopped

      if (ctx->expected_status && g_strcmp0(content, ctx->expected_status) == 0) {
        result = "done";
      } else if (g_strcmp0(content, "fail") == 0) {
        result = "fail";
      } else if (g_strcmp0(content, "stopped") == 0) {
        result = "stopped";
      } else {
        // it is best for the sake of resilience to ignore partial values
        g_free(content);
        return;
      }

      ctx->callback(result, ctx->user_data);
      g_free(content);
    }
  }
}

int service_management_subscribe_job_removed(ServiceManagementContext *ctx,
                                             service_job_completed_cb callback,
                                             gpointer user_data) {
  GFile *file = g_file_new_for_path(STATUS_FILE);
  ctx->callback = callback;
  ctx->user_data = user_data;

  ctx->monitor = g_file_monitor_file(file, G_FILE_MONITOR_NONE, NULL, NULL);
  g_object_unref(file);

  if (!ctx->monitor) {
    dnsconfd_log(LOG_ERR, "Failed to watch unbound status file");
    return -1;
  }

  ctx->handler_id = g_signal_connect(ctx->monitor, "changed", G_CALLBACK(on_file_changed), ctx);
  return 0;
}
