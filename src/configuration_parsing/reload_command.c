#include "reload_command.h"

#include <argp.h>

#include "dnsconfd_config.h"

static char doc[] = "Reload DNS backend provider";
static char args_doc[] = "[-h]";

static struct argp_option options[] = {{0}};

static error_t parse_reload_command_opt(int key, char *arg, struct argp_state *state) {
  switch (key) {
  case ARGP_KEY_ARG:
    argp_error(state, "Reload does not accept subcommands");
    break;
  case ARGP_KEY_END:
    break;
  default:
    return ARGP_ERR_UNKNOWN;
  }
  return 0;
}

static struct argp argp_reload_command = {options, parse_reload_command_opt, args_doc, doc};

error_t parse_reload_command(int argc, char *argv[]) {
  return argp_parse(&argp_reload_command, argc, argv, ARGP_IN_ORDER, 0, 0);
}
