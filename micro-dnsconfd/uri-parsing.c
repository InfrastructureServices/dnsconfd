#include "uri-parsing.h"

#include <arpa/inet.h>
#include <curl/curl.h>
#include <gio/gio.h>

static unsigned char is_valid_ip(char *ip) {
  struct in_addr inaddr;
  struct in6_addr inaddr6;
  return (inet_pton(AF_INET, ip, &inaddr) || inet_pton(AF_INET6, ip, &inaddr6));
}

unsigned char transform_server_string(gchar *server_string, unsigned char *is_server_tls,
                                      GString *unbound_config_string, FILE *log_file) {
  CURLU *server_curl_handle = curl_url();
  CURLUcode parser_rc;

  char *scheme = 0;
  char *host = 0;
  char *port = 0;
  char *fragment = 0;

  unsigned char scheme_error = 0;

  parser_rc = curl_url_set(server_curl_handle, CURLUPART_URL, server_string,
                           CURLU_DEFAULT_SCHEME | CURLU_NON_SUPPORT_SCHEME);

  if (parser_rc != CURLUE_OK) {
    fprintf(log_file, "Could not parse server url\n");
    curl_url_cleanup(server_curl_handle);
    return 1;
  }

  parser_rc = curl_url_get(server_curl_handle, CURLUPART_SCHEME, &scheme, 0);
  if (parser_rc != CURLUE_OK) {
    fprintf(log_file, "Could not parse server scheme\n");
    curl_url_cleanup(server_curl_handle);
    return 1;
  }

  if (!strcmp(scheme, "dns+udp") || !strcmp(scheme, "dns+tcp") ||
      (!strcmp(scheme, "https") && strncmp(server_string, "https", 5))) {
    *is_server_tls = 0;
  } else if (!strcmp(scheme, "dns+tls")) {
    *is_server_tls = 1;
  } else {
    fprintf(log_file, "Server using unsupported scheme\n");
    scheme_error = 1;
  }
  curl_free(scheme);
  if (scheme_error) {
    curl_url_cleanup(server_curl_handle);
    return 1;
  }

  parser_rc = curl_url_get(server_curl_handle, CURLUPART_HOST, &host, 0);
  if (parser_rc != CURLUE_OK) {
    fprintf(log_file, "Could not parse server host\n");
    curl_url_cleanup(server_curl_handle);
    return 1;
  }

  // unbound unfortunately does not accept ipv6 enclosed in square brackets,
  // so if they are present, then remove them
  if (host[0] == '[') {
    // remove last character
    host[strlen(host) - 1] = 0;
    // on host pointer we will copy address without the first character [
    memmove(host, host + 1, strlen(host) + 1);
  }
  if (!is_valid_ip(host)) {
    fprintf(log_file, "Host is not a valid ip address\n");
    curl_free(host);
    curl_url_cleanup(server_curl_handle);
    return 1;
  }

  g_string_append_printf(unbound_config_string, "\tforward-addr: %s", host);
  curl_free(host);

  parser_rc = curl_url_get(server_curl_handle, CURLUPART_PORT, &port, 0);
  if (parser_rc != CURLUE_OK && parser_rc != CURLUE_NO_PORT) {
    fprintf(log_file, "Could not parse server port\n");
    curl_url_cleanup(server_curl_handle);
    return 1;
  }

  if (port) {
    g_string_append_printf(unbound_config_string, "@%s", port);
    curl_free(port);
  }

  parser_rc = curl_url_get(server_curl_handle, CURLUPART_FRAGMENT, &fragment, 0);
  curl_url_cleanup(server_curl_handle);

  if (parser_rc != CURLUE_OK && parser_rc != CURLUE_NO_FRAGMENT) {
    fprintf(log_file, "Could not parse server fragment\n");
    return 1;
  }

  if (fragment) {
    g_string_append_printf(unbound_config_string, "#%s", fragment);
    curl_free(fragment);
  }
  g_string_append_printf(unbound_config_string, "\n");

  return 0;
}