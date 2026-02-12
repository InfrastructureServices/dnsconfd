#include <argp.h>

#include "dnsconfd_config.h"

#ifndef CONFIG_COMMAND_H
#define CONFIG_COMMAND_H

error_t parse_config_command(int argc, char* argv[], config_command_options_t* config);

#endif
