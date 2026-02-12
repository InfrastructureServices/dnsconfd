#include <dbus_server.h>
#include <unistd.h>

#include "cli_commands/cli_config.h"
#include "cli_commands/cli_update.h"
#include "cli_commands/cli_common.h"
#include "dnsconfd_config.h"
#include "log_utilities.h"

int main(int argc, char* argv[]) {
  dnsconfd_config_t config;
  int exit_code = 0;

  // we will log errors during parsing of configuration to stderr
  // after configuration is in place, we will use more sophisticated methods

  if (parse_configuration(argc, argv, &config)) {
    exit_code = EXIT_BAD_ARGUMENTS;
    goto finish;
  }

  switch (config.command) {
    case COMMAND_START:
      // now open logs;
      if (initialize_logs(&config)) {
        exit_code = EXIT_LOGS;
        goto finish;
      }
      exit_code = dbus_server_run(&config);
      close_logs(&config);
      break;
    case COMMAND_STATUS:
      exit_code = cli_execute_simple_command("Status");
      break;
    case COMMAND_RELOAD:
      exit_code = cli_execute_simple_command("Reload");
      break;
    case COMMAND_CONFIG:
      exit_code = cli_config_command(&config);
      break;
    case COMMAND_UPDATE:
      exit_code = cli_update_command(&config);
      break;
  }

finish:
  config_cleanup(&config);
  return exit_code;
}
