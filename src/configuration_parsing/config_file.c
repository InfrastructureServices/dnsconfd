#include "config_file.h"

#include <arpa/inet.h>
#include <string.h>
#include <syslog.h>
#include <yaml.h>

#include "config_utils.h"
#include "dnsconfd_config.h"
#include "ip_utilities.h"
#include "log_utilities.h"
#include "types/network_address.h"
#include "types/server_uri.h"

static dns_protocol_t parse_protocol_string(const char* str) {
  if (strcmp(str, "dns+udp") == 0) return DNS_UDP;
  if (strcmp(str, "dns+tcp") == 0) return DNS_TCP;
  if (strcmp(str, "dns+tls") == 0) return DNS_TLS;
  return DNS_PROTOCOLS_END;
}

static int parse_priority_str(const char* str, server_uri_t* server) {
  long temp_long;
  char* end_char;

  temp_long = strtol(str, &end_char, 10);
  if (temp_long < INT_MIN || temp_long > INT_MAX || *end_char != '\0') {
    return -1;
  }

  server->priority = (int)temp_long;

  return 0;
}

static int parse_port_str(const char* str, struct sockaddr_storage* address) {
  long temp_long;
  char* end_char;

  temp_long = strtol(str, &end_char, 10);
  if (temp_long < 0 || temp_long > 65535 || *end_char != '\0') {
    return -1;
  }

  if (address->ss_family == AF_INET) {
    ((struct sockaddr_in*)address)->sin_port = htons((uint16_t)temp_long);
  } else {
    ((struct sockaddr_in6*)address)->sin6_port = htons((uint16_t)temp_long);
  }

  return 0;
}

static int parse_domains(yaml_parser_t* parser, GList** dest_list) {
  yaml_event_t event;
  int done = 0;
  char* domain;

  while (!done) {
    if (!yaml_parser_parse(parser, &event)) return -1;

    switch (event.type) {
      case YAML_SCALAR_EVENT:
        if (!(domain = strdup((const char*)event.data.scalar.value))) {
          yaml_event_delete(&event);
          return -1;
        }
        *dest_list = g_list_append(*dest_list, domain);
        break;

      case YAML_SEQUENCE_END_EVENT:
        done = 1;
        break;

      default:
        break;
    }

    yaml_event_delete(&event);
  }
  return 0;
}

static int parse_networks(yaml_parser_t* parser, GList** dest_list) {
  yaml_event_t event;
  int done = 0;
  network_address_t* network;

  while (!done) {
    if (!yaml_parser_parse(parser, &event)) return -1;

    switch (event.type) {
      case YAML_SCALAR_EVENT:
        if (!(network = malloc(sizeof(network_address_t)))) {
          yaml_event_delete(&event);
          return -1;
        }
        if (network_address_t_from_string((const char*)event.data.scalar.value, network) != 0) {
          free(network);
          yaml_event_delete(&event);
          return -1;
        }
        *dest_list = g_list_append(*dest_list, network);
        break;

      case YAML_SEQUENCE_END_EVENT:
        done = 1;
        break;

      default:
        break;
    }

    yaml_event_delete(&event);
  }
  return 0;
}

static int parse_static_servers(yaml_parser_t* parser, dnsconfd_config_t* config,
                                const char** error_string) {
  yaml_event_t event;
  int done = 0;
  int status = 0;
  server_uri_t* current_server = NULL;
  char* current_key = NULL;
  int expect_key = 1;

  while (!done) {
    if (!yaml_parser_parse(parser, &event)) {
      *error_string = "Failed to parse configuration YAML";
      status = -1;
      break;
    }

    switch (event.type) {
      case YAML_SEQUENCE_START_EVENT:
        if (current_server && current_key) {
          if (strcmp(current_key, "routing_domains") == 0) {
            if (parse_domains(parser, &current_server->routing_domains) != 0) {
              *error_string = "Failed to parse routing_domains in static_servers";
              status = -1;
            }
          } else if (strcmp(current_key, "search_domains") == 0) {
            if (parse_domains(parser, &current_server->search_domains) != 0) {
              *error_string = "Failed to parse search_domains in static_servers";
              status = -1;
            }
          } else if (strcmp(current_key, "networks") == 0) {
            if (parse_networks(parser, &current_server->networks) != 0) {
              *error_string = "Failed to parse networks in static_servers";
              status = -1;
            }
          } else {
            *error_string = "Unrecognized sequence in static_servers";
            status = -1;
          }
          free(current_key);
          current_key = NULL;
          expect_key = 1;
        } else {
          *error_string = "Badly formatted static_servers";
          status = -1;
        }
        break;
      case YAML_MAPPING_START_EVENT:
        if (current_server) {
          *error_string = "Badly formatted static_servers";
          status = -1;
        } else {
          current_server = calloc(1, sizeof(server_uri_t));
          if (!current_server) {
            *error_string = "Failed to allocate memory for static_servers";
            status = -1;
          } else {
            current_server->dnssec = 1;
          }
        }
        break;

      case YAML_MAPPING_END_EVENT:
        if (current_server) {
          if (current_server->address.ss_family == PF_UNSPEC) {
            *error_string = "Server in static_servers does not have address set";
            status = -1;
          }

          if (!current_server->routing_domains) {
            current_server->routing_domains = g_list_append(NULL, strdup("."));
          }

          set_default_port(&current_server->address,
                           current_server->protocol != DNS_TLS ? 53 : 853);
          config->static_servers = g_list_append(config->static_servers, current_server);
          current_server = NULL;
        }
        break;

      case YAML_SCALAR_EVENT:
        if (expect_key) {
          current_key = strdup((char*)event.data.scalar.value);
          expect_key = 0;
        } else {
          if (current_server && current_key) {
            if (strcmp(current_key, "name") == 0) {
              current_server->name = strdup((const char*)event.data.scalar.value);
            } else if (strcmp(current_key, "protocol") == 0) {
              current_server->protocol =
                  parse_protocol_string((const char*)event.data.scalar.value);
              if (current_server->protocol == DNS_PROTOCOLS_END) status = -1;
            } else if (strcmp(current_key, "address") == 0) {
              if (parse_ip_str((const char*)event.data.scalar.value, &current_server->address)) {
                *error_string = "Failed to parse address in static_servers";
                status = -1;
              }
            } else if (strcmp(current_key, "port") == 0) {
              if (parse_port_str((const char*)event.data.scalar.value, &current_server->address)) {
                *error_string = "Failed to parse port in static_servers";
                status = -1;
              }
            } else if (strcmp(current_key, "dnssec") == 0) {
              if (strcmp((const char*)event.data.scalar.value, "1") != 0 &&
                  strcmp((const char*)event.data.scalar.value, "yes") != 0) {
                current_server->dnssec = 0;
              }
            } else if (strcmp(current_key, "priority") == 0) {
              if (parse_priority_str((const char*)event.data.scalar.value, current_server)) {
                *error_string = "Failed to parse priority in static_servers";
                status = -1;
              }
            } else {
              *error_string = "Unrecognized field in static_servers";
              status = -1;
            }
          }
          free(current_key);
          current_key = NULL;
          expect_key = 1;
        }
        break;

      case YAML_SEQUENCE_END_EVENT:
        done = 1;
        break;

      default:
        break;
    }

    yaml_event_delete(&event);
    if (status != 0) break;
  }

  if (status != 0) {
    if (current_key) free(current_key);
    if (current_server) server_uri_t_destroy(current_server);
  }
  return status;
}

static int duplicating_options(const char* key, const char* value, dnsconfd_config_t* config,
                               const char** error_string) {
  struct {
    const char* opt_key;
    const char** destination;
  } options[] = {{"file_log", &config->file_log},
                 {"resolv_conf_path", &config->resolv_conf_path},
                 {"resolver_options", &config->resolver_options},
                 {"certification_authority", &config->certification_authority}};

  for (size_t i = 0; i < sizeof(options) / sizeof(options[0]); i++) {
    if (strcmp(key, options[i].opt_key) == 0) {
      if (*options[i].destination) {
        free((void*)*options[i].destination);
      }
      if ((*options[i].destination = strdup(value)) == NULL) {
        *error_string = "Failed to allocate memory for option during config parsing";
        return -1;
      } else {
        return 0;
      }
    }
  }
  *error_string = "Unrecognized option present in configuration YAML";
  return -1;
}

int parse_config_file(const char* path, dnsconfd_config_t* config, const char** error_string) {
  unsigned int temp_val;
  yaml_parser_t parser;
  yaml_event_t event;
  int done = 0;
  int status = 0;
  char* current_key = NULL;
  int depth = 0;
  int expect_key = 1;

  FILE* fh = fopen(path, "r");
  if (fh == NULL) {
    *error_string = "Failed to open configuration file";
    return -1;
  }

  if (!yaml_parser_initialize(&parser)) {
    *error_string = "Failed to initialize YAML parser";
    fclose(fh);
    return -1;
  }

  yaml_parser_set_input_file(&parser, fh);

  while (!done) {
    if (!yaml_parser_parse(&parser, &event)) {
      *error_string = "Failed parse configuration YAML";
      status = -1;
      break;
    }

    switch (event.type) {
      case YAML_MAPPING_START_EVENT:
        depth++;
        if (depth > 1) {
          *error_string = "Badly formatted YAML";
          status = -1;
          done = 1;
        }
        break;
      case YAML_SEQUENCE_START_EVENT:
        if (current_key && strcmp(current_key, "static_servers") == 0) {
          if (parse_static_servers(&parser, config, error_string) != 0) {
            status = -1;
          }
          free(current_key);
          current_key = NULL;
          expect_key = 1;
        }
        break;

      case YAML_SCALAR_EVENT:
        if (expect_key) {
          if ((current_key = strdup((char*)event.data.scalar.value)) == NULL) {
            *error_string = "Failed to allocate memory during YAML parsing";
            status = -1;
            break;
          }
          expect_key = 0;
        } else {
          if (strcmp(current_key, "log_level") == 0) {
            if ((temp_val = parse_log_level((const char*)event.data.scalar.value)) < 0) {
              *error_string = "Failed to parse log level in configuration";
              status = -1;
            } else {
              config->log_level = temp_val;
            }
          } else if (strcmp(current_key, "stderr_log") == 0) {
            config->stderr_log = parse_boolean((const char*)event.data.scalar.value);
          } else if (strcmp(current_key, "syslog_log") == 0) {
            config->syslog_log = parse_boolean((const char*)event.data.scalar.value);
          } else if (strcmp(current_key, "listen_address") == 0) {
            if (parse_ip_str((const char*)event.data.scalar.value, &config->listen_address) != 0) {
              *error_string = "Failed to parse listen address in configuration";
              status = -1;
            }
          } else if (strcmp(current_key, "prioritize_wire") == 0) {
            config->prioritize_wire = parse_boolean((const char*)event.data.scalar.value);
          } else if (strcmp(current_key, "dnssec_enabled") == 0) {
            config->dnssec_enabled = parse_boolean((const char*)event.data.scalar.value);
          } else {
            status = duplicating_options(current_key, (const char*)event.data.scalar.value, config,
                                         error_string);
          }

          done = status ? 1 : 0;
          free(current_key);
          current_key = NULL;
          expect_key = 1;
        }

        break;

      case YAML_STREAM_END_EVENT:
        done = 1;
        break;

      default:
        break;
    }

    yaml_event_delete(&event);
    if (status != 0) done = 1;
  }

  if (current_key) free(current_key);
  yaml_parser_delete(&parser);
  fclose(fh);
  return status;
}
