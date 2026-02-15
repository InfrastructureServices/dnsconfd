#include "dnsconfd_config.h"
#include <stdarg.h>

#ifndef LOG_UTILITIES_H
#define LOG_UTILITIES_H

int parse_log_level(const char *arg);

int initialize_logs(dnsconfd_config_t *config);

void dnsconfd_log(int level, dnsconfd_config_t *config, const char *format, ...);

void close_logs(dnsconfd_config_t *config);

#endif /* LOG_UTILITIES_H */
