#include <argp.h>
#include <string.h>

#include "dnsconfd_config.h"
#include "status_command.h"

static char doc[] = "Perform system configuration actions related to Dnsconfd";
static char args_doc[] = "[-h] "
                         "<nm_enable|nm_disable|take_resolvconf|return_"
                         "resolvconf|install|uninstall>";

static struct argp_option options[] = {{0}};

static error_t parse_config_command_opt(int key, char *arg, struct argp_state *state) {
  config_command_options_t *config = (config_command_options_t *)state->input;

  switch (key) {
  case ARGP_KEY_ARG:
    if (config->action != CONFIG_ACTION_NONE) {
      argp_error(state, "Command of config was already specified");
    }
    if (strcasecmp(arg, "nm_enable") == 0) {
      config->action = CONFIG_ACTION_NM_ENABLE;
    } else if (strcasecmp(arg, "nm_disable") == 0) {
      config->action = CONFIG_ACTION_NM_DISABLE;
    } else if (strcasecmp(arg, "take_resolvconf") == 0) {
      config->action = CONFIG_ACTION_TAKE_RESOLVCONF;
    } else if (strcasecmp(arg, "return_resolvconf") == 0) {
      config->action = CONFIG_ACTION_RETURN_RESOLVCONF;
    } else if (strcasecmp(arg, "install") == 0) {
      config->action = CONFIG_ACTION_INSTALL;
    } else if (strcasecmp(arg, "uninstall") == 0) {
      config->action = CONFIG_ACTION_UNINSTALL;
    } else {
      argp_error(state, "Unknown config command: %s", arg);
    }
    break;
  case ARGP_KEY_END:
    if (config->action == CONFIG_ACTION_NONE) {
      argp_error(state, "Config requires subcommand");
    }
    break;
  default:
    return ARGP_ERR_UNKNOWN;
  }
  return 0;
}

static struct argp argp_config_command = {options, parse_config_command_opt, args_doc, doc};

error_t parse_config_command(int argc, char *argv[], config_command_options_t *config) {
  return argp_parse(&argp_config_command, argc, argv, ARGP_IN_ORDER, 0, config);
}
