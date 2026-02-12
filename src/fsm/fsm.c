#include "fsm.h"

#include <gio/gio.h>
#include <stdio.h>
#include <syslog.h>
#include <systemd/sd-daemon.h>

#include "dns_managers/unbound_manager.h"
#include "log_utilities.h"
#include "service_management.h"
#include "types/server_uri.h"

const char* fsm_state_t_to_string(fsm_state_t state) {
  switch (state) {
    case FSM_STARTING:
      return "STARTING";
      break;
    case FSM_CONFIGURING_DNS_MANAGER:
      return "CONFIGURING_DNS_MANAGER";
      break;
    case FSM_SUBMITTING_START_JOB:
      return "SUBMITTING_START_JOB";
      break;
    case FSM_WAITING_FOR_START_JOB:
      return "WAITING_FOR_START_JOB";
      break;
    case FSM_SETTING_RESOLV_CONF:
      return "SETTING_RESOLV_CONF";
      break;
    case FSM_UPDATING_DNS_MANAGER:
      return "UPDATING_DNS_MANAGER";
      break;
    case FSM_RUNNING:
      return "RUNNING";
      break;
    case FSM_REVERTING_RESOLV_CONF:
      return "REVERTING_RESOLV_CONF";
      break;
    case FSM_SUBMITTING_STOP_JOB:
      return "SUBMITTING_STOP_JOB";
      break;
    case FSM_WAITING_STOP_JOB:
      return "WAITING_STOP_JOB";
      break;
    case FSM_STOPPING:
      return "STOPPING";
      break;
    default:
      return "UNKNOWN";
      break;
  }
}

const char* fsm_event_t_to_string(fsm_event_t event) {
  switch (event) {
    case EVENT_NONE:
      return "NONE";
      break;
    case EVENT_UPDATE:
      return "UPDATE";
      break;
    case EVENT_KICKOFF:
      return "KICKOFF";
      break;
    case EVENT_SUCCESS:
      return "SUCCESS";
      break;
    case EVENT_FAILURE:
      return "FAILURE";
      break;
    case EVENT_RELOAD:
      return "RELOAD";
      break;
    case EVENT_JOB_SUCCESS:
      return "JOB_SUCCESS";
      break;
    case EVENT_JOB_FAILURE:
      return "JOB_FAILURE";
      break;
    case EVENT_STOP:
      return "STOP";
      break;
    default:
      return "UNKNOWN";
      break;
  }
}

const char* dnsconfd_mode_t_to_string(dnsconfd_mode_t mode) {
  switch (mode) {
    case MODE_BACKUP:
      return "backup";
      break;
    case MODE_PREFER:
      return "prefer";
      break;
    case MODE_EXCLUSIVE:
      return "exclusive";
      break;
    default:
      return "unknown";
      break;
  }
}

static void set_dynamic_servers(fsm_context_t* ctx) {
  if (ctx->current_dynamic_servers) {
    g_list_free_full(ctx->current_dynamic_servers, server_uri_t_destroy);
  }

  ctx->current_dynamic_servers = ctx->new_dynamic_servers;
  ctx->new_dynamic_servers = NULL;
}

static fsm_event_t update_context(fsm_context_t* ctx) {
  dnsconfd_log(LOG_DEBUG, ctx->config, "Refreshing server structures");

  if (ctx->all_servers) {
    g_list_free(ctx->all_servers);
  }

  ctx->all_servers = g_list_concat(g_list_copy(ctx->config->static_servers),
                                   g_list_copy(ctx->current_dynamic_servers));

  if (ctx->current_domain_to_servers) {
    g_hash_table_destroy(ctx->current_domain_to_servers);
  }

  ctx->current_domain_to_servers = server_list_to_hash_table(ctx->all_servers);

  // branchless increment of configuration serial while keeping it > 1
  ctx->requested_configuration_serial += 1 + ((ctx->requested_configuration_serial + 1) == 0);

  return EVENT_NONE;
}

static fsm_event_t fsm_starting_event_kickoff(fsm_context_t* ctx) {
  const char* error_string = NULL;
  update_context(ctx);

  if (write_configuration(ctx, &error_string)) {
    if (error_string) {
      dnsconfd_log(LOG_ERR, ctx->config, error_string);
    }
    dnsconfd_log(LOG_ERR, ctx->config, "Failed to create dns cache configuration");
    return EVENT_FAILURE;
  }

  return EVENT_SUCCESS;
}

static void on_systemd_job_finished(unsigned int id, const char* result, gpointer user_data) {
  fsm_context_t* ctx = (fsm_context_t*)user_data;
  if (ctx->awaited_systemd_job != id) return;
  service_management_unsubscribe_job_removed(ctx->dbus_connection, ctx->systemd_subscription_id);
  ctx->awaited_systemd_job = 0;
  ctx->systemd_subscription_id = 0;

  if (strcmp(result, "done") == 0 || strcmp(result, "skipped") == 0) {
    state_transition(ctx, EVENT_JOB_SUCCESS);
  } else {
    dnsconfd_log(LOG_ERR, ctx->config, "Awaited systemd job failed");
    state_transition(ctx, EVENT_JOB_FAILURE);
  }
}

static fsm_event_t fsm_configuring_dns_manager_event_success(fsm_context_t* ctx) {
  GError* error = NULL;

  if (!ctx->systemd_subscription_id) {
    ctx->systemd_subscription_id = service_management_subscribe_job_removed(
        ctx->dbus_connection, on_systemd_job_finished, ctx);
    if (!ctx->systemd_subscription_id) {
      dnsconfd_log(LOG_ERR, ctx->config, "Failed to subscribe to systemd job removed signal");
      return EVENT_FAILURE;
    }
  }

  ctx->awaited_systemd_job = service_start(ctx->dbus_connection, "unbound.service", &error);

  if (!ctx->awaited_systemd_job) {
    dnsconfd_log(LOG_ERR, ctx->config, "Failed to submit DNS cache start job");
    if (error) {
      dnsconfd_log(LOG_ERR, ctx->config, "%s", error->message);
      g_error_free(error);
    }
    return EVENT_FAILURE;
  }
  return EVENT_SUCCESS;
}

static fsm_event_t set_resolv_conf(fsm_context_t* ctx) {
  const char* error_string = NULL;

  if (write_resolv_conf(ctx->config, ctx->current_domain_to_servers, &ctx->resolv_conf_backup,
                        ctx->resolution_mode, &error_string)) {
    if (error_string) {
      dnsconfd_log(LOG_ERR, ctx->config, error_string);
    }
    dnsconfd_log(LOG_ERR, ctx->config, "Failed to write resolv.conf");
    return EVENT_FAILURE;
  }
  return EVENT_SUCCESS;
}

static void emit_configuration_serial_signal(fsm_context_t* ctx) {
  GVariantBuilder builder;
  g_variant_builder_init(&builder, G_VARIANT_TYPE("a{sv}"));
  g_variant_builder_add(&builder, "{sv}", "configuration_serial",
                        g_variant_new_uint32(ctx->current_configuration_serial));

  g_dbus_connection_emit_signal(ctx->dbus_connection, NULL, "/com/redhat/dnsconfd",
                                "org.freedesktop.DBus.Properties", "PropertiesChanged",
                                g_variant_new("(sa{sv}@as)", "com.redhat.dnsconfd.Manager",
                                              &builder, g_variant_new_strv(NULL, 0)),
                                NULL);
}

static fsm_event_t update_dns_manager(fsm_context_t* ctx) {
  GHashTable* new_unbound_domain_to_servers;
  const char* error_string = NULL;

  switch (update(ctx, &new_unbound_domain_to_servers, &error_string)) {
    case 0:
      if (ctx->current_unbound_domain_to_servers) {
        g_hash_table_destroy(ctx->current_unbound_domain_to_servers);
      }
      ctx->current_unbound_domain_to_servers = new_unbound_domain_to_servers;
      ctx->current_configuration_serial = ctx->requested_configuration_serial;
      sd_notify(0, "READY=1\n");
      emit_configuration_serial_signal(ctx);
      return EVENT_SUCCESS;
      break;
    case 1:
      return EVENT_RELOAD;
      break;
    default:
      if (error_string) {
        dnsconfd_log(LOG_ERR, ctx->config, error_string);
      }
      dnsconfd_log(LOG_ERR, ctx->config, "Failed to update dns cache service");
      return EVENT_FAILURE;
      break;
  }
}

static fsm_event_t submit_stop_job(fsm_context_t* ctx) {
  GError* error = NULL;

  if (!ctx->systemd_subscription_id) {
    ctx->systemd_subscription_id = service_management_subscribe_job_removed(
        ctx->dbus_connection, on_systemd_job_finished, ctx);
    if (!ctx->systemd_subscription_id) {
      dnsconfd_log(LOG_ERR, ctx->config, "Failed to subscribe to systemd job removed signal");
      return EVENT_FAILURE;
    }
  }

  ctx->awaited_systemd_job = service_stop(ctx->dbus_connection, "unbound.service", &error);

  if (!ctx->awaited_systemd_job) {
    dnsconfd_log(LOG_ERR, ctx->config, "Failed to submit dns cache service stop job");
    if (error) {
      dnsconfd_log(LOG_ERR, ctx->config, "%s", error->message);
      g_error_free(error);
    }
    return EVENT_FAILURE;
  }

  return EVENT_SUCCESS;
}

static fsm_event_t revert_resolv_conf(fsm_context_t* ctx) {
  FILE* resolv_conf_file = fopen(ctx->config->resolv_conf_path, "w");

  if (!resolv_conf_file || fprintf(resolv_conf_file, "%s", ctx->resolv_conf_backup->str) < 0) {
    dnsconfd_log(LOG_ERR, ctx->config, "Failed to revert resolv.conf");
    return EVENT_FAILURE;
  }

  return EVENT_SUCCESS;
}

static void set_exit_code(fsm_context_t* ctx, exit_code_t code) {
  if (ctx->exit_code == 0) {
    ctx->exit_code = code;
  }
}

// -1 error 0 continue 1 halt
int state_transition(fsm_context_t* ctx, fsm_event_t event) {
  fsm_event_t cur_event = event;

  do {
    dnsconfd_log(LOG_NOTICE, ctx->config, "Performing transition from %s on %s",
                 fsm_state_t_to_string(ctx->current_state), fsm_event_t_to_string(cur_event));
    switch (ctx->current_state) {
      case FSM_STARTING:
        switch (cur_event) {
          case EVENT_UPDATE:
            set_dynamic_servers(ctx);
            cur_event = update_context(ctx);
            break;
          case EVENT_KICKOFF:
            cur_event = fsm_starting_event_kickoff(ctx);
            ctx->current_state = FSM_CONFIGURING_DNS_MANAGER;
            break;
          case EVENT_RELOAD:
            cur_event = EVENT_NONE;
            break;
          case EVENT_STOP:
            ctx->current_state = FSM_STOPPING;
            break;
          default:
            return -1;
            break;
        }
        break;
      case FSM_CONFIGURING_DNS_MANAGER:
        switch (cur_event) {
          case EVENT_SUCCESS:
            cur_event = fsm_configuring_dns_manager_event_success(ctx);
            ctx->current_state = FSM_SUBMITTING_START_JOB;
            break;
          case EVENT_FAILURE:
            ctx->current_state = FSM_STOPPING;
            cur_event = EVENT_STOP;
            break;
          default:
            return -1;
            break;
        }
        break;
      case FSM_SUBMITTING_START_JOB:
        switch (cur_event) {
          case EVENT_SUCCESS:
            ctx->current_state = FSM_WAITING_FOR_START_JOB;
            cur_event = EVENT_NONE;
            break;
          case EVENT_FAILURE:
            ctx->current_state = FSM_STOPPING;
            cur_event = EVENT_STOP;
            break;
          default:
            return -1;
            break;
        }
        break;
      case FSM_WAITING_FOR_START_JOB:
        switch (cur_event) {
          case EVENT_JOB_SUCCESS:
            ctx->current_state = FSM_SETTING_RESOLV_CONF;
            cur_event = set_resolv_conf(ctx);
            break;
          case EVENT_JOB_FAILURE:
            // TODO log failure of start job
            set_exit_code(ctx, EXIT_SERVICE_FAILURE);
            ctx->current_state = FSM_STOPPING;
            cur_event = EVENT_STOP;
            break;
          case EVENT_UPDATE:
            set_dynamic_servers(ctx);
            cur_event = update_context(ctx);
            break;
          case EVENT_RELOAD:
            ctx->current_state = FSM_CONFIGURING_DNS_MANAGER;
            cur_event = fsm_starting_event_kickoff(ctx);
            break;
          case EVENT_STOP:
            ctx->current_state = FSM_SUBMITTING_STOP_JOB;
            cur_event = submit_stop_job(ctx);
            break;
          default:
            return -1;
            break;
        }
        break;
      case FSM_SETTING_RESOLV_CONF:
        switch (cur_event) {
          case EVENT_SUCCESS:
            ctx->current_state = FSM_UPDATING_DNS_MANAGER;
            cur_event = update_dns_manager(ctx);
            break;
          case EVENT_FAILURE:
            set_exit_code(ctx, EXIT_RESOLV_CONF_FAILURE);
            ctx->current_state = FSM_SUBMITTING_STOP_JOB;
            cur_event = submit_stop_job(ctx);
            break;
          default:
            return -1;
            break;
        }
        break;
      case FSM_UPDATING_DNS_MANAGER:
        switch (cur_event) {
          case EVENT_SUCCESS:
            ctx->current_state = FSM_RUNNING;
            cur_event = EVENT_NONE;
            break;
          case EVENT_FAILURE:
            set_exit_code(ctx, EXIT_UPDATE_FAILURE);
            ctx->current_state = FSM_REVERTING_RESOLV_CONF;
            cur_event = revert_resolv_conf(ctx);
            break;
          case EVENT_RELOAD:
            sd_notify(0, "RELOADING=1\n");
            ctx->current_state = FSM_CONFIGURING_DNS_MANAGER;
            cur_event = fsm_starting_event_kickoff(ctx);
            break;
          default:
            return -1;
            break;
        }
        break;
      case FSM_RUNNING:
        switch (cur_event) {
          case EVENT_UPDATE:
            set_dynamic_servers(ctx);
            update_context(ctx);
            ctx->current_state = FSM_SETTING_RESOLV_CONF;
            cur_event = set_resolv_conf(ctx);
            break;
          case EVENT_RELOAD:
            sd_notify(0, "RELOADING=1\n");
            ctx->current_state = FSM_CONFIGURING_DNS_MANAGER;
            cur_event = fsm_starting_event_kickoff(ctx);
            break;
          case EVENT_STOP:
            ctx->current_state = FSM_REVERTING_RESOLV_CONF;
            cur_event = revert_resolv_conf(ctx);
            break;
          default:
            return -1;
            break;
        }
        break;
      case FSM_REVERTING_RESOLV_CONF:
        switch (cur_event) {
          case EVENT_FAILURE:
          case EVENT_SUCCESS:
            ctx->current_state = FSM_SUBMITTING_STOP_JOB;
            cur_event = submit_stop_job(ctx);
            break;
          default:
            return -1;
            break;
        }
        break;
      case FSM_SUBMITTING_STOP_JOB:
        switch (cur_event) {
          case EVENT_SUCCESS:
            ctx->current_state = FSM_WAITING_STOP_JOB;
            cur_event = EVENT_NONE;
            break;
          case EVENT_FAILURE:
            ctx->current_state = FSM_STOPPING;
            cur_event = EVENT_STOP;
            break;
          default:
            return -1;
            break;
        }
        break;
      case FSM_WAITING_STOP_JOB:
        switch (cur_event) {
          case EVENT_JOB_FAILURE:
          case EVENT_JOB_SUCCESS:
            ctx->current_state = FSM_STOPPING;
            cur_event = EVENT_STOP;
            break;
          case EVENT_UPDATE:
          case EVENT_RELOAD:
          case EVENT_STOP:
            cur_event = EVENT_NONE;
            break;
          default:
            return -1;
            break;
        }
        break;
      case FSM_STOPPING:
        switch (cur_event) {
          case EVENT_STOP:
            g_main_loop_quit(ctx->main_loop);
            cur_event = EVENT_NONE;
            break;
          default:
            return -1;
            break;
        }
        break;
    }
  } while (cur_event);

  dnsconfd_log(LOG_DEBUG, ctx->config, "Sleeping on state %s",
               fsm_state_t_to_string(ctx->current_state));

  return 0;
}
