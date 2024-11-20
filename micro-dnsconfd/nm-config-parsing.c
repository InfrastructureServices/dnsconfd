#include "nm-config-parsing.h"

#include <gio/gio.h>
#include <stdio.h>

#include "uri-parsing.h"

static GVariantDict *get_domain_dict(GVariant *domain_value, FILE *log_file) {
  GVariantDict *domain_dict;
  if (!g_variant_type_equal(g_variant_get_type(domain_value),
                            G_VARIANT_TYPE("a{sv}"))) {
    fprintf(log_file, "Unexpected member of domains field\n");
    return NULL;
  }

  domain_dict = g_variant_dict_new(domain_value);
  if (!domain_dict) {
    fprintf(log_file, "Out of memory");
  }
  return domain_dict;
}

static unsigned char create_unbound_conf(GVariantDict *glob_dict,
                                         GString *unbound_config_string,
                                         const char *fallback_ca,
                                         FILE *log_file) {
  unsigned char global_specified = 0;

  GVariantIter domains_iter;
  gchar *domain_name;

  GVariant *domain_value;
  GVariantDict *domain_dict;

  GVariant *servers;
  GVariantIter server_iter;

  gchar *server_string;

  unsigned int tls_servers;
  unsigned int non_tls_servers;
  unsigned char is_server_tls;

  unsigned char rc;
  GVariant *certification_authority;
  gchar *certification_authority_string;

  GVariant *domains = g_variant_dict_lookup_value(glob_dict, "domains",
                                                  G_VARIANT_TYPE_DICTIONARY);

  if (!domains) {
    fprintf(log_file, "No global domains specified in configuration\n");
    return 1;
  }

  g_string_append(
      unbound_config_string,
      "server:\n\tmodule-config: \"ipsecmod iterator\"\n\tinterface: "
      "127.0.0.1\n\tdo-not-query-address: 127.0.0.1/8\n");

  certification_authority = g_variant_dict_lookup_value(
      glob_dict, "certification-authority", G_VARIANT_TYPE_STRING);

  if (certification_authority) {
    g_variant_get(certification_authority, "&s",
                  &certification_authority_string);
    g_string_append_printf(unbound_config_string, "\ttls-cert-bundle: %s\n",
                           certification_authority_string);
    g_variant_unref(certification_authority);
  } else {
    g_string_append_printf(unbound_config_string, "\ttls-cert-bundle: %s\n",
                           fallback_ca);
  }

  if (!g_variant_iter_init(&domains_iter, domains)) {
    fprintf(log_file, "No domain specified in configuration\n");
    return 1;
  }

  while (
      g_variant_iter_next(&domains_iter, "{sv}", &domain_name, &domain_value)) {
    if (strcmp(domain_name, "*") != 0) {
      g_string_append_printf(unbound_config_string,
                             "forward-zone:\n\tname: \"%s\"\n", domain_name);
    } else {
      global_specified = 1;
      g_string_append(unbound_config_string, "forward-zone:\n\tname: \".\"\n");
    }
    g_free(domain_name);

    domain_dict = get_domain_dict(domain_value, log_file);
    g_variant_unref(domain_value);
    if (!domain_dict) {
      g_variant_unref(domains);
      return 1;
    }

    servers = g_variant_dict_lookup_value(domain_dict, "servers",
                                          G_VARIANT_TYPE_ARRAY);
    g_variant_dict_unref(domain_dict);

    if (!servers || !g_variant_iter_init(&server_iter, servers)) {
      fprintf(log_file, "No servers specified for domain\n");
      g_variant_unref(domains);
      return 1;
    }

    tls_servers = 0;
    non_tls_servers = 0;

    while (g_variant_iter_next(&server_iter, "&s", &server_string)) {
      rc = transform_server_string(server_string, &is_server_tls,
                                   unbound_config_string, log_file);
      if (rc) {
        g_variant_unref(domains);
        g_variant_unref(servers);
        return 1;
      }
      if (is_server_tls) {
        tls_servers++;
      } else {
        non_tls_servers++;
      }
    }
    g_variant_unref(servers);

    if (tls_servers) {
      if (non_tls_servers) {
        fprintf(log_file, "Can not combine tls and non-tls servers\n");
        g_variant_unref(domains);
        return 1;
      }
      g_string_append(unbound_config_string, "\tforward-tls-upstream: yes\n");
    }
  }

  g_variant_unref(domains);

  if (!global_specified) {
    g_string_append(
        unbound_config_string,
        "forward-zone:\n\tname: \".\"\n\tforward-addr: 127.0.0.1\n");
  }
  return 0;
}

static void parse_resolv_field(GVariantDict *glob_dict,
                               GString *resolvconf_string, char *dict_key,
                               char *resolv_field) {
  GVariantIter iter;
  GVariant *array;
  gchar *cur_value;
  array =
      g_variant_dict_lookup_value(glob_dict, dict_key, G_VARIANT_TYPE_ARRAY);
  if (array) {
    if (g_variant_iter_init(&iter, array)) {
      g_string_append_printf(resolvconf_string, "%s", resolv_field);
      while (g_variant_iter_next(&iter, "s", &cur_value)) {
        g_string_append_printf(resolvconf_string, " %s", cur_value);
        g_free(cur_value);
      }
      g_string_append(resolvconf_string, "\n");
    }
    g_variant_unref(array);
  }
}

static void create_resolv_conf(GVariantDict *glob_dict,
                               GString *resolvconf_string) {
  g_string_append(resolvconf_string, "nameserver 127.0.0.1\n");
  parse_resolv_field(glob_dict, resolvconf_string, "options", "options");
  parse_resolv_field(glob_dict, resolvconf_string, "searches", "search");
}

GString *get_unbound_conf_string(GVariantDict *glob_dict,
                                 const char *fallback_ca, FILE *log_file) {
  GString *unbound_config_string = g_string_new(NULL);
  if (!unbound_config_string) {
    fprintf(log_file, "Out of memory\n");
    return NULL;
  }

  if (create_unbound_conf(glob_dict, unbound_config_string, fallback_ca,
                          log_file)) {
    g_string_free(unbound_config_string, 1);
    return NULL;
  }

  return unbound_config_string;
}

GString *get_resolv_conf_string(GVariantDict *glob_dict, FILE *log_file) {
  GString *resolvconf_string = g_string_new(NULL);
  if (!resolvconf_string) {
    fprintf(log_file, "Out of memory\n");
    return NULL;
  }

  create_resolv_conf(glob_dict, resolvconf_string);
  return resolvconf_string;
}
