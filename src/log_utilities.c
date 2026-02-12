#include "log_utilities.h"

#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include <syslog.h>

int parse_log_level(const char* arg) {
  if (strcasecmp(arg, "debug") == 0) return LOG_DEBUG;
  if (strcasecmp(arg, "info") == 0) return LOG_INFO;
  if (strcasecmp(arg, "notice") == 0) return LOG_NOTICE;
  if (strcasecmp(arg, "warning") == 0) return LOG_WARNING;
  if (strcasecmp(arg, "err") == 0 || strcasecmp(arg, "error") == 0) return LOG_ERR;
  if (strcasecmp(arg, "crit") == 0) return LOG_CRIT;
  if (strcasecmp(arg, "alert") == 0) return LOG_ALERT;
  if (strcasecmp(arg, "emerg") == 0) return LOG_EMERG;

  return -1;
}

typedef enum {
  LOG_TO_STDERR = 1,
  LOG_TO_SYSLOG = 2,
  LOG_TO_FILE = 4,
} log_switch_values_t;

int initialize_logs(dnsconfd_config_t* config) {
  int syslog_flags;
  int stderr_syslog_handled = 0;

  if (config->syslog_log == CONFIG_BOOLEAN_TRUE) {
    syslog_flags = LOG_CONS | LOG_NDELAY | LOG_PID |
                   (config->stderr_log == CONFIG_BOOLEAN_TRUE ? LOG_PERROR : 0);
    stderr_syslog_handled = config->stderr_log == CONFIG_BOOLEAN_TRUE;
    config->log_switch = LOG_TO_SYSLOG;
    openlog("dnsconfd", syslog_flags, LOG_DAEMON);
  }

  config->log_switch |=
      (!stderr_syslog_handled && config->stderr_log == CONFIG_BOOLEAN_TRUE) ? LOG_TO_STDERR : 0;

  if (config->file_log) {
    config->log_switch |= LOG_TO_FILE;
    config->opened_log_file = fopen(config->file_log, "a");
    if (!config->opened_log_file) {
      fprintf(stderr, "Failed to open log file %s", config->file_log);
      return -1;
    }
  }

  return 0;
}

void dnsconfd_log(int level, dnsconfd_config_t* config, const char* format, ...) {
  va_list args;

  if (level > config->log_level) return;

  if (config->log_switch & LOG_TO_SYSLOG) {
    va_start(args, format);
    vsyslog(level, format, args);
    va_end(args);
  } else if (config->log_switch & LOG_TO_STDERR) {
    va_start(args, format);
    vfprintf(stderr, format, args);
    fprintf(stderr, "\n");
    va_end(args);
  }

  if (config->log_switch & LOG_TO_FILE) {
    va_start(args, format);
    vfprintf(config->opened_log_file, format, args);
    fprintf(config->opened_log_file, "\n");
    fflush(config->opened_log_file);
    va_end(args);
  }
}

void close_logs(dnsconfd_config_t* config) {
  if (config->opened_log_file) {
    fclose(config->opened_log_file);
  }
  if (config->syslog_log == CONFIG_BOOLEAN_TRUE) {
    closelog();
  }
}
