#include "status_command.h"

#include <argp.h>

#include "dnsconfd_config.h"

static char doc[] = "Show status of running dnsconfd instance";
static char args_doc[] = "[-h] [--json]";

enum {
  OPT_JSON = 1000,
};

static struct argp_option options[] = {
    {"json", OPT_JSON, 0, 0, "Print status in JSON format"},
    {0},
};

static error_t parse_status_command_opt(int key, char* arg, struct argp_state* state) {
  status_command_options_t* config = (status_command_options_t*)state->input;

  switch (key) {
    case OPT_JSON:
      config->json = 1;
      break;
    case ARGP_KEY_ARG:
      argp_error(state, "Status does not take any further subcommand: %s", arg);
      break;
    case ARGP_KEY_END:
      break;
    default:
      return ARGP_ERR_UNKNOWN;
  }
  return 0;
}

static struct argp argp_status_command = {options, parse_status_command_opt, args_doc, doc};

error_t parse_status_command(int argc, char* argv[], status_command_options_t* config) {
  return argp_parse(&argp_status_command, argc, argv, ARGP_IN_ORDER, 0, config);
}
