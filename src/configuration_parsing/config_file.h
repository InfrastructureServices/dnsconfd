#include "dnsconfd_config.h"

#ifndef CONFIG_FILE_H
#define CONFIG_FILE_H

int parse_config_file(const char* path, dnsconfd_config_t* config, const char** error_string);

#endif /* CONFIG_FILE_H */
