#include <argp.h>
#include <arpa/inet.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>
#include <syslog.h>

#include "config_command.h"
#include "config_file.h"
#include "dnsconfd_config.h"
#include "environment_config.h"
#include "ip_utilities.h"
#include "log_utilities.h"
#include "reload_command.h"
#include "status_command.h"
#include "types/server_uri.h"
#include "update_command.h"

error_t argp_err_exit_status = EXIT_BAD_ARGUMENTS;
const char *argp_program_version = "dnsconfd 2.0.0";
const char *argp_program_bug_address = "<tkorbar@redhat.com>";
static char doc[] = "local DNS cache configuration daemon";
static char args_doc[] = "[--help] [--log-level LOG_LEVEL] [--stderr-log | --no-stderr-log] "
                         "[--syslog-log SYSLOG_LOG] [--file-log FILE_LOG] "
                         "[--resolv-conf-path RESOLV_CONF_PATH] [--listen-address LISTEN_ADDRESS] "
                         "[--prioritize-wire | --no-prioritize-wire] [--resolver-options "
                         "RESOLVER_OPTIONS] "
                         "[--dnssec-enabled | --no-dnssec-enabled] "
                         "[--config-file CONFIG_FILE] [--certification-authority "
                         "CERTIFICATION_AUTHORITY] "
                         "{status,reload,config,update} ...";

enum {
  OPT_LOG_LEVEL = 1000,
  OPT_STDERR_LOG,
  OPT_NO_STDERR_LOG,
  OPT_SYSLOG_LOG,
  OPT_NO_SYSLOG_LOG,
  OPT_FILE_LOG,
  OPT_RESOLV_CONF_PATH,
  OPT_LISTEN_ADDRESS,
  OPT_PRIORITIZE_WIRE,
  OPT_NO_PRIORITIZE_WIRE,
  OPT_RESOLVER_OPTIONS,
  OPT_DNSSEC_ENABLED,
  OPT_NO_DNSSEC_ENABLED,
  OPT_CONFIG_FILE,
  OPT_CERTIFICATION_AUTHORITY
};

static struct argp_option options[] = {
    {"log-level", OPT_LOG_LEVEL, "[debug|info|notice|warning|error|crit|alert|emerg]", 0,
     "Log level of dnsconfd, Default is info"},
    {"stderr-log", OPT_STDERR_LOG, 0, 0, "Log to stderr, this is the default"},
    {"no-stderr-log", OPT_NO_STDERR_LOG, 0, 0, "Do not log to stderr"},
    {"syslog-log", OPT_SYSLOG_LOG, 0, 0, "Log to syslog, this is turned off by default"},
    {"no-syslog-log", OPT_NO_SYSLOG_LOG, 0, 0, "Do not log to syslog"},
    {"file-log", OPT_FILE_LOG, "FILE_LOG", 0,
     "Path to the log file, this is turned off by default"},
    {"resolv-conf-path", OPT_RESOLV_CONF_PATH, "RESOLV_CONF_PATH", 0,
     "Path to resolv.conf that the dnsconfd should manage, Default is "
     "/etc/resolv.conf"},
    {"listen-address", OPT_LISTEN_ADDRESS, "LISTEN_ADDRESS", 0,
     "Address on which local resolver listens, Default is 127.0.0.1"},
    {"prioritize-wire", OPT_PRIORITIZE_WIRE, 0, 0,
     "Wireless interfaces will have lower priority, this is the default"},
    {"no-prioritize-wire", OPT_NO_PRIORITIZE_WIRE, 0, 0,
     "All interfaces will have the same priority"},
    {"resolver-options", OPT_RESOLVER_OPTIONS, "RESOLVER_OPTIONS", 0,
     "Options to be used in resolv.conf for alteration of resolver behavior, "
     "default is edns0 "
     "trust-ad"},
    {"dnssec-enabled", OPT_DNSSEC_ENABLED, 0, 0, "Enable dnssec record validation"},
    {"no-dnssec-enabled", OPT_NO_DNSSEC_ENABLED, 0, 0,
     "Do not enable dnssec record validation, this is the default"},
    {"config-file", OPT_CONFIG_FILE, "CONFIG_FILE", 0,
     "Path where config file is located, default is /etc/dnsconfd.conf"},
    {"certification-authority", OPT_CERTIFICATION_AUTHORITY, "CERTIFICATION_AUTHORITY", 0,
     "Space separated list of CA bundles used for encrypted protocols as "
     "default when no custom CA "
     "was specified. The first one that can be accessed will be used, Default "
     "is "
     "/etc/pki/dns/extracted/pem/tls-ca-bundle.pem "
     "/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem"},
    {0}};

static error_t parse_global_opt(int key, char *arg, struct argp_state *state) {
  dnsconfd_config_t *config = state->input;
  error_t subcommand_parsing_result = 0;

  switch (key) {
  case OPT_LOG_LEVEL:
    if ((config->log_level = parse_log_level(arg)) < 0) {
      argp_error(state, "Invalid log level: %s", arg);
    }
    break;
  case OPT_STDERR_LOG:
    config->stderr_log = CONFIG_BOOLEAN_TRUE;
    break;
  case OPT_NO_STDERR_LOG:
    config->stderr_log = CONFIG_BOOLEAN_FALSE;
    break;
  case OPT_SYSLOG_LOG:
    config->syslog_log = CONFIG_BOOLEAN_TRUE;
    break;
  case OPT_NO_SYSLOG_LOG:
    config->syslog_log = CONFIG_BOOLEAN_FALSE;
    break;
  case OPT_FILE_LOG:
    if (config->file_log != NULL) {
      free((char *)config->file_log);
    }
    if ((config->file_log = strdup(arg)) == NULL) {
      return ENOMEM;
    }
    break;
  case OPT_RESOLV_CONF_PATH:
    if (config->resolv_conf_path != NULL) {
      free((char *)config->resolv_conf_path);
    }
    if ((config->resolv_conf_path = strdup(arg)) == NULL) {
      return ENOMEM;
    }
    break;
  case OPT_LISTEN_ADDRESS:
    if (parse_ip_str(arg, &config->listen_address) != 0) {
      argp_error(state, "Invalid listen address: %s", arg);
    }
    break;
  case OPT_PRIORITIZE_WIRE:
    config->prioritize_wire = CONFIG_BOOLEAN_TRUE;
    break;
  case OPT_NO_PRIORITIZE_WIRE:
    config->prioritize_wire = CONFIG_BOOLEAN_FALSE;
    break;
  case OPT_RESOLVER_OPTIONS:
    if (config->resolver_options != NULL) {
      free((char *)config->resolver_options);
    }
    if ((config->resolver_options = strdup(arg)) == NULL) {
      return ENOMEM;
    }
    break;
  case OPT_DNSSEC_ENABLED:
    config->dnssec_enabled = CONFIG_BOOLEAN_TRUE;
    break;
  case OPT_NO_DNSSEC_ENABLED:
    config->dnssec_enabled = CONFIG_BOOLEAN_FALSE;
    break;
  case OPT_CONFIG_FILE:
    if (config->config_file != NULL) {
      free((char *)config->config_file);
    }
    if ((config->config_file = strdup(arg)) == NULL) {
      return ENOMEM;
    }
    break;
  case OPT_CERTIFICATION_AUTHORITY:
    if (config->certification_authority != NULL) {
      free((char *)config->certification_authority);
    }
    if ((config->certification_authority = strdup(arg)) == NULL) {
      return ENOMEM;
    }
    break;
  case ARGP_KEY_ARG:
    if (config->command != COMMAND_START) {
      argp_error(state, "Command was already specified %s", arg);
    }
    if (strcasecmp(arg, "status") == 0) {
      config->command = COMMAND_STATUS;
      subcommand_parsing_result =
          parse_status_command(state->argc - state->next + 1, &state->argv[state->next - 1],
                               &config->command_options.status_options);
    } else if (strcasecmp(arg, "reload") == 0) {
      config->command = COMMAND_RELOAD;
      subcommand_parsing_result =
          parse_reload_command(state->argc - state->next + 1, &state->argv[state->next - 1]);
    } else if (strcasecmp(arg, "config") == 0) {
      config->command = COMMAND_CONFIG;
      subcommand_parsing_result =
          parse_config_command(state->argc - state->next + 1, &state->argv[state->next - 1],
                               &config->command_options.config_options);
    } else if (strcasecmp(arg, "update") == 0) {
      config->command = COMMAND_UPDATE;
      subcommand_parsing_result =
          parse_update_command(state->argc - state->next + 1, &state->argv[state->next - 1],
                               &config->command_options.update_options);
    } else {
      argp_error(state, "Unknown command: %s", arg);
    }
    if (subcommand_parsing_result) {
      return subcommand_parsing_result;
    }
    state->next = state->argc;
    break;
  case ARGP_KEY_END:
    break;
  default:
    return ARGP_ERR_UNKNOWN;
  }
  return 0;
}

static struct argp argp = {options, parse_global_opt, args_doc, doc};

static void merge_configs(dnsconfd_config_t *high_prio, dnsconfd_config_t *low_prio) {
  size_t i = 0;
  struct {
    const char **high;
    const char *low;
  } str_to_check[] = {{&high_prio->file_log, low_prio->file_log},
                      {&high_prio->resolv_conf_path, low_prio->resolv_conf_path},
                      {&high_prio->resolver_options, low_prio->resolver_options},
                      {&high_prio->config_file, low_prio->config_file},
                      {&high_prio->certification_authority, low_prio->certification_authority}};
  struct {
    config_boolean_t *high;
    config_boolean_t *low;
  } bools_to_check[] = {
      {&high_prio->stderr_log, &low_prio->stderr_log},
      {&high_prio->syslog_log, &low_prio->syslog_log},
      {&high_prio->prioritize_wire, &low_prio->prioritize_wire},
      {&high_prio->dnssec_enabled, &low_prio->dnssec_enabled},
  };

  for (i = 0; i < sizeof(str_to_check) / sizeof(str_to_check[0]); i++) {
    if (!(*str_to_check[i].high)) {
      *str_to_check[i].high = str_to_check[i].low;
    } else {
      if (str_to_check[i].low)
        free((void *)str_to_check[i].low);
    }
  }

  if (!high_prio->static_servers) {
    high_prio->static_servers = low_prio->static_servers;
  } else {
    g_list_free_full(low_prio->static_servers, (GDestroyNotify)server_uri_t_destroy);
  }

  if (high_prio->listen_address.ss_family == PF_UNSPEC) {
    high_prio->listen_address = low_prio->listen_address;
  }

  if (high_prio->log_level < 0) {
    high_prio->log_level = low_prio->log_level;
  }

  for (i = 0; i < sizeof(bools_to_check) / sizeof(bools_to_check[0]); i++) {
    if (*bools_to_check[i].high == CONFIG_BOOLEAN_UNSET) {
      *bools_to_check[i].high = *bools_to_check[i].low;
    }
  }
}

int parse_configuration(int argc, char *argv[], dnsconfd_config_t *config) {
  const char *error_string;
  dnsconfd_config_t temp_config = (dnsconfd_config_t){0};
  temp_config.log_level = -1;
  *config = temp_config;

  // We will have two configs in place always, one with higher priority,
  // the other with lower, if the higher one has something unspecified,
  // it will be replaced by values from lower ones

  if (argp_parse(&argp, argc, argv, ARGP_IN_ORDER, 0, config) != 0) {
    return 1;
  }

  if (parse_environment_variables(&temp_config, &error_string) != 0) {
    fprintf(stderr, "%s\n", error_string);
    return 1;
  }

  // this operation at the end clears temp_config members if neccessary
  merge_configs(config, &temp_config);

  if (!config->config_file) {
    if (!(config->config_file = strdup("/etc/dnsconfd.conf")))
      return 1;
  }

  temp_config = (dnsconfd_config_t){0};
  temp_config.log_level = -1;

  if (parse_config_file(config->config_file, &temp_config, &error_string) != 0) {
    fprintf(stderr, "%s\n", error_string);
    return 1;
  }

  merge_configs(config, &temp_config);

  if (config->log_level < 0) {
    config->log_level = LOG_INFO;
  }
  if (config->stderr_log == CONFIG_BOOLEAN_UNSET) {
    config->stderr_log = CONFIG_BOOLEAN_TRUE;
  }
  if (config->syslog_log == CONFIG_BOOLEAN_UNSET) {
    config->syslog_log = CONFIG_BOOLEAN_FALSE;
  }
  if (!config->resolv_conf_path) {
    if (!(config->resolv_conf_path = strdup("/etc/resolv.conf")))
      return 1;
  }
  if (config->listen_address.ss_family == PF_UNSPEC) {
    // Default listen address 127.0.0.1
    ((struct sockaddr_in *)&config->listen_address)->sin_family = AF_INET;
    inet_pton(AF_INET, "127.0.0.1", &((struct sockaddr_in *)&config->listen_address)->sin_addr);
  }
  if (config->prioritize_wire == CONFIG_BOOLEAN_UNSET) {
    config->prioritize_wire = CONFIG_BOOLEAN_TRUE;
  }
  if (config->dnssec_enabled == CONFIG_BOOLEAN_UNSET) {
    config->dnssec_enabled = CONFIG_BOOLEAN_FALSE;
  }
  if (!config->resolver_options) {
    if (!(config->resolver_options = strdup("edns0 trust-ad")))
      return 1;
  }

  if (!config->certification_authority) {
    if (!(config->certification_authority =
              strdup("/etc/pki/dns/extracted/pem/tls-ca-bundle.pem "
                     "/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem")))
      return 1;
  }

  return 0;
}

void config_cleanup(dnsconfd_config_t *config) {
  const char *pointers_to_check[5] = {config->file_log, config->resolv_conf_path,
                                      config->resolver_options, config->config_file,
                                      config->certification_authority};

  for (size_t i = 0; i < 5; i++) {
    if (pointers_to_check[i] != NULL) {
      free((char *)pointers_to_check[i]);
    }
  }

  if (config->command == COMMAND_UPDATE) {
    update_command_options_t_free_update_lists(&config->command_options.update_options);
  }

  if (config->static_servers) {
    g_list_free_full(config->static_servers, (GDestroyNotify)server_uri_t_destroy);
  }
}
