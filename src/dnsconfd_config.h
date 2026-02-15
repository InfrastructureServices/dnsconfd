#include <glib.h>
#include <netinet/in.h>
#include <stdio.h>

#ifndef DNSCONFD_CONFIG_H
#define DNSCONFD_CONFIG_H

typedef enum {
  EXIT_OK = 0,
  EXIT_SERVICE_FAILURE = 8,
  EXIT_DBUS_FAILURE = 9,
  EXIT_RESOLV_CONF_FAILURE = 10,
  EXIT_CONFIG_FAILURE = 11,
  EXIT_BAD_ARGUMENTS = 13,
  EXIT_LOGS = 14,
  EXIT_COMMAND_FAILURE = 15,
  EXIT_UPDATE_FAILURE = 16,
  EXIT_FSM_FAILURE = 17,
} exit_code_t;

typedef enum {
  COMMAND_START = 0,
  COMMAND_STATUS,
  COMMAND_RELOAD,
  COMMAND_CONFIG,
  COMMAND_UPDATE,
} dnsconfd_command_t;

typedef enum {
  MODE_BACKUP = 0,
  MODE_PREFER,
  MODE_EXCLUSIVE,
} dnsconfd_mode_t;

typedef enum {
  CONFIG_ACTION_NONE = 0,
  CONFIG_ACTION_NM_ENABLE,
  CONFIG_ACTION_NM_DISABLE,
  CONFIG_ACTION_TAKE_RESOLVCONF,
  CONFIG_ACTION_RETURN_RESOLVCONF,
  CONFIG_ACTION_INSTALL,
  CONFIG_ACTION_UNINSTALL,
} config_action_t;

typedef struct {
  config_action_t action;
} config_command_options_t;

typedef struct {
  unsigned char json;
} status_command_options_t;

typedef struct {
  dnsconfd_mode_t mode;
  unsigned char json;
  GList *servers_uris;
} update_command_options_t;

typedef union {
  status_command_options_t status_options;
  update_command_options_t update_options;
  config_command_options_t config_options;
} command_options_t;

typedef enum {
  CONFIG_BOOLEAN_UNSET = 0,
  CONFIG_BOOLEAN_TRUE,
  CONFIG_BOOLEAN_FALSE
} config_boolean_t;

typedef struct {
  const char *file_log;
  const char *resolv_conf_path;
  const char *resolver_options;
  const char *config_file;
  const char *certification_authority;
  FILE *opened_log_file;
  GList *static_servers;
  struct sockaddr_storage listen_address;
  dnsconfd_command_t command;
  command_options_t command_options;
  int8_t log_level;
  int8_t log_switch;
  config_boolean_t stderr_log;
  config_boolean_t syslog_log;
  config_boolean_t prioritize_wire;
  config_boolean_t dnssec_enabled;
} dnsconfd_config_t;

int parse_configuration(int argc, char *argv[], dnsconfd_config_t *config);

void config_cleanup(dnsconfd_config_t *config);

#endif
