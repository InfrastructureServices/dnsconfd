#include "update_command.h"

#include <argp.h>
#include <stdlib.h>
#include <string.h>

#include "dnsconfd_config.h"
#include "types/server_uri.h"

static char doc[] = "Update DNS configuration";
static char args_doc[] =
    "[--help] [--json] [--mode <backup|prefer|exclusive>] [<SERVERS_JSON> | <SERVER_URIS>]";

enum { OPT_JSON = 1000, OPT_MODE };

static struct argp_option options[] = {
    {"json", OPT_JSON, 0, 0, "Servers will be supplied as JSON string instead of URIs"},
    {"mode", OPT_MODE, "MODE", 0, "Resolving mode (backup, prefer, exclusive)"},
    {0},
};

void update_command_options_t_free_update_lists(update_command_options_t* config) {
  if (config->servers_uris) {
    g_list_free_full(config->servers_uris, server_uri_t_destroy);
  }
}

static error_t parse_update_command_opt(int key, char* arg, struct argp_state* state) {
  server_uri_t* new_server;
  update_command_options_t* config = (update_command_options_t*)state->input;
  static int parsed_as_json = 0;

  switch (key) {
    case OPT_JSON:
      config->json = 1;
      break;
    case OPT_MODE:
      if (strcasecmp(arg, "backup") == 0) {
        // backup is the default so just continue
        break;
      } else if (strcasecmp(arg, "prefer") == 0) {
        config->mode = MODE_PREFER;
      } else if (strcasecmp(arg, "exclusive") == 0) {
        config->mode = MODE_EXCLUSIVE;
      } else {
        argp_error(state, "Invalid mode: %s", arg);
      }
      break;
    case ARGP_KEY_ARG:
      if (parsed_as_json != 0) {
        // we already parsed a string as JSON, thus this is error
        argp_error(state, "When JSON was enabled, only one string is allowed");
      }
      if (config->json) {
        config->servers_uris = server_uri_t_list_from_json(arg);
        if (!config->servers_uris) {
          argp_error(state, "Servers JSON is badly formed");
        }
        parsed_as_json = 1;
        break;
      }
      if ((new_server = malloc(sizeof(server_uri_t))) == NULL) {
        return ENOMEM;
      }
      if (server_uri_t_init_from_string(arg, new_server) != 0) {
        argp_error(state, "Badly formated URI %s", arg);
      }
      config->servers_uris = g_list_append(config->servers_uris, new_server);
      break;
    case ARGP_KEY_END:
      break;
    default:
      return ARGP_ERR_UNKNOWN;
  }
  return 0;
}

static struct argp argp_update_command = {options, parse_update_command_opt, args_doc, doc};

error_t parse_update_command(int argc, char* argv[], update_command_options_t* config) {
  return argp_parse(&argp_update_command, argc, argv, ARGP_IN_ORDER, 0, config);
}
