#ifndef ENVIRONMENT_CONFIG_H
#define ENVIRONMENT_CONFIG_H

#include "dnsconfd_config.h"

int parse_environment_variables(dnsconfd_config_t* config, const char **error_string);

#endif
