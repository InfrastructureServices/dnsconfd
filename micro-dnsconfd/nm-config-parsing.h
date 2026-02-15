#include <gio/gio.h>
#include <stdio.h>

#ifndef NM_CONFIG_PARSING_H_
#define NM_CONFIG_PARSING_H_

GString *get_unbound_conf_string(GVariantDict *glob_dict, const char *fallback_ca, FILE *log_file);
GString *get_resolv_conf_string(GVariantDict *glob_dict, FILE *log_file);

#endif
