#include <argp.h>

#include "dnsconfd_config.h"

#ifndef UPDATE_COMMAND_H
#define UPDATE_COMMAND_H

error_t parse_update_command(int argc, char* argv[], update_command_options_t* config);

void update_command_options_t_free_update_lists(update_command_options_t* config);

#endif

