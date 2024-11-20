#include <argp.h>
#include <gio/gio.h>
#include <glib.h>
#include <limits.h>
#include <stdio.h>

#include "dbus-handling.h"
#include "arg-parsing.h"
#include "output-handling.h"
#include "nm-config-parsing.h"

int main(int argc, char *argv[]) {
  arguments args = {.resolvconf = NULL, .unboundconf = NULL, .call_notify = 0};
  // dictionary of NetworkManager global options
  GVariantDict *glob_dict;
  GString *resolv_conf_string;
  GString *unbound_conf_string;
  char output_rc = 0;

  if (parse_args(argc, argv, &args) != 0) {
    return 1;
  }

  if (!(glob_dict = get_glob_dict(&glob_dict))) {
    return 1;
  }

  if (!(unbound_conf_string = get_unbound_conf_string(glob_dict, stderr))) {
    g_variant_dict_unref(glob_dict);
    return 1;
  }

  resolv_conf_string = get_resolv_conf_string(glob_dict, stderr);
  g_variant_dict_unref(glob_dict);

  if (!resolv_conf_string) {
    g_string_free(unbound_conf_string, 1);
    return 1;
  }

  output_rc = handle_output(args.unboundconf, unbound_conf_string);
  g_string_free(unbound_conf_string, 1);

  if(output_rc) {
    g_string_free(resolv_conf_string, 1);
    return 1;
  }

  /// if both files are going to stdout then we need to divide them somehow
  if (!args.resolvconf && !args.unboundconf) {
    fprintf(stdout, "###\n");
  }

  output_rc = handle_output(args.resolvconf, resolv_conf_string);
  g_string_free(resolv_conf_string, 1);

  return output_rc;
}
