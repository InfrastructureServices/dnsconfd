#include <gio/gio.h>
#include <stdio.h>

#ifndef URI_PARSING_H
#define URI_PARSING_H

unsigned char transform_server_string(gchar *server_string, unsigned char *is_server_tls,
                                      GString *unbound_config_string, FILE *log_file);
#endif
