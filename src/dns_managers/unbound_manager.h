#include <glib.h>

#include "dnsconfd_config.h"
#include "fsm/fsm.h"

#ifndef UNBOUND_MANAGER_H
#define UNBOUND_MANAGER_H

int write_configuration(fsm_context_t* ctx, const char **error_string);

int write_resolv_conf(dnsconfd_config_t* config, GHashTable* domain_to_servers, GString** backup,
                      dnsconfd_mode_t mode, const char** error_string);

int update(fsm_context_t* ctx, GHashTable** result, const char **error_string);

#endif /* UNBOUND_MANAGER_H */
