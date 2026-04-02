#ifndef CLI_COMMON_H
#define CLI_COMMON_H

#include <gio/gio.h>

GDBusConnection *cli_connect_to_dbus();
int cli_call_simple_method(GDBusConnection *connection, const char *method_name,
                           unsigned char json);
int cli_execute_simple_command(const char *method_name, unsigned char json);

#endif
