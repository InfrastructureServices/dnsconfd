#include <argp.h>

#include "dnsconfd_config.h"

#ifndef STATUS_COMMAND_H
#define STATUS_COMMAND_H

error_t parse_status_command(int argc, char* argv[], status_command_options_t* config);

#endif
