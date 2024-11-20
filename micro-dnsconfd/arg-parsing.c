#include "arg-parsing.h"

#include <argp.h>

// these two can not be static, because they are already declared in argp.h
const char *argp_program_version = "micro-dnsconfd";
const char *argp_program_bug_address = "<tkorbar@redhat.com>";

static char doc[] = "Generator of resolv.conf and unbound configuration, "
                    "parsing NM global config";
static char args_doc[] = "[-r <path_to_resolvconf>] [-u <path_to_unbound_conf]";
static struct argp_option options[] = {
    {"resolvconf", 'r', "resolv.conf", 0, "Path to resolv.conf file"},
    {"unboundconf", 'u', "unbound.conf", 0,
     "Path to unbound configuration file"},
    {"no-error-code", 'n', 0, 0, "Do not exit with error code on error"},
    {0}};

static error_t parse_opt(int key, char *arg, struct argp_state *state) {
  struct arguments *arguments = state->input;
  switch (key) {
  case 'r':
    arguments->resolvconf = arg;
    break;
  case 'u':
    arguments->unboundconf = arg;
    break;
  case 'n':
    arguments->no_error_code = 1;
    break;
  case ARGP_KEY_ARG:
    return 0;
  default:
    return ARGP_ERR_UNKNOWN;
  }
  return 0;
}

static struct argp argp = {options, parse_opt, args_doc, doc, 0, 0, 0};

error_t parse_args(int argc, char *argv[], arguments *args) {
  return argp_parse(&argp, argc, argv, 0, 0, args);
}
