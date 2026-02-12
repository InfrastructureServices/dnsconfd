#include <gio/gio.h>

#include "dnsconfd_config.h"

#ifndef FSM_H
#define FSM_H

typedef enum {
  FSM_STARTING = 0,
  FSM_CONFIGURING_DNS_MANAGER,
  FSM_SUBMITTING_START_JOB,
  FSM_WAITING_FOR_START_JOB,
  FSM_SETTING_RESOLV_CONF,
  FSM_UPDATING_DNS_MANAGER,
  FSM_RUNNING,
  FSM_REVERTING_RESOLV_CONF,
  FSM_SUBMITTING_STOP_JOB,
  FSM_WAITING_STOP_JOB,
  FSM_STOPPING,
} fsm_state_t;

typedef enum {
  EVENT_NONE = 0,
  EVENT_UPDATE,
  EVENT_KICKOFF,
  EVENT_SUCCESS,
  EVENT_FAILURE,
  EVENT_RELOAD,
  EVENT_JOB_SUCCESS,
  EVENT_JOB_FAILURE,
  EVENT_STOP,
} fsm_event_t;

typedef struct {
  fsm_state_t current_state;
  dnsconfd_config_t* config;
  GList* current_dynamic_servers;
  GList* new_dynamic_servers;
  GList* all_servers;
  GHashTable* current_domain_to_servers;
  GHashTable* current_unbound_domain_to_servers;
  GDBusConnection* dbus_connection;
  GString* resolv_conf_backup;
  char* effective_ca;
  GMainLoop* main_loop;
  unsigned int awaited_systemd_job;
  unsigned int systemd_subscription_id;
  unsigned int exit_code;
  unsigned int requested_configuration_serial;
  unsigned int current_configuration_serial;
  dnsconfd_mode_t resolution_mode;
} fsm_context_t;

int state_transition(fsm_context_t* ctx, fsm_event_t event);

const char* fsm_state_t_to_string(fsm_state_t state);

const char* fsm_event_t_to_string(fsm_event_t event);

const char *dnsconfd_mode_t_to_string(dnsconfd_mode_t mode);

#endif /* FSM_H */
