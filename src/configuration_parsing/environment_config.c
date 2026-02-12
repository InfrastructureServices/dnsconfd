#include "environment_config.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "ip_utilities.h"
#include "log_utilities.h"

static unsigned char parse_boolean(const char* str) {
  return strcmp(str, "yes") == 0 || strcmp(str, "1") == 0 ? CONFIG_BOOLEAN_TRUE
                                                          : CONFIG_BOOLEAN_FALSE;
}

int parse_environment_variables(dnsconfd_config_t* config, const char **error_string) {
  char* env_val;
  size_t i;

  struct {
    const char* opt_key;
    const char** destination;
  } string_options[] = {{"FILE_LOG", &config->file_log},
                        {"RESOLV_CONF_PATH", &config->resolv_conf_path},
                        {"RESOLVER_OPTIONS", &config->resolver_options},
                        {"CERTIFICATION_AUTHORITY", &config->certification_authority},
                        {"CONFIG_FILE", &config->config_file}};
  struct {
    const char* opt_key;
    config_boolean_t* destination;
  } boolean_options[] = {{"STDERR_LOG", &config->stderr_log},
                         {"SYSLOG_LOG", &config->syslog_log},
                         {"PRIORITIZE_WIRE", &config->prioritize_wire},
                         {"DNSSEC_ENABLED", &config->dnssec_enabled}};

  for (i = 0; i < sizeof(string_options) / sizeof(string_options[0]); i++) {
    if ((env_val = getenv(string_options[i].opt_key))) {
      if ((*string_options[i].destination = strdup(env_val)) == NULL) {
        *error_string = "Failed to allocate space for option in environment variables";
        return -1;
      }
    }
  }

  for (i = 0; i < sizeof(boolean_options) / sizeof(boolean_options[0]); i++) {
    if ((env_val = getenv(boolean_options[i].opt_key))) {
      *boolean_options[i].destination = parse_boolean(env_val);
    }
  }

  if ((env_val = getenv("LOG_LEVEL"))) {
    if ((config->log_level = parse_log_level(env_val)) < 0) {
      *error_string = "Failed to parse log level in environment variables";
      return -1;
    }
  }

  if ((env_val = getenv("LISTEN_ADDRESS"))) {
    if (parse_ip_str(env_val, &config->listen_address) != 0) {
      *error_string = "Failed to parse listen address from environmental variables";
      return -1;
    }
  }

  return 0;
}
