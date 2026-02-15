#include "test-nm-config-parsing.h"

#include <check.h>
#include <stdio.h>

#include "nm-config-parsing.h"

typedef struct {
  const gchar *options[4];
  const gchar *searches[4];
  const char *output;
} resolv_conf_tuple;

static resolv_conf_tuple resolv_conf_cases[] = {
    {{"edns0", "trust-ad", NULL},
     {"example.org", "example.com", NULL},
     "nameserver 127.0.0.1\noptions edns0 trust-ad\nsearch example.org "
     "example.com\n"},
    {{NULL},
     {"example.org", "example.com", NULL},
     "nameserver 127.0.0.1\nsearch example.org example.com\n"},
    {{"edns0", "trust-ad", NULL}, {NULL}, "nameserver 127.0.0.1\noptions edns0 trust-ad\n"},
    {{NULL}, {NULL}, "nameserver 127.0.0.1\n"},
    {{"edns0", NULL},
     {"example.org", NULL},
     "nameserver 127.0.0.1\noptions edns0\nsearch example.org\n"},
    {{0}}};

START_TEST(test_get_resolv_conf_string) {
  GVariantDict *glob_dict;
  GString *resolvconf_content;
  const char *cur_output = resolv_conf_cases[0].output;
  FILE *devnull = fopen("/dev/null", "w");

  for (int i = 0; cur_output != NULL; i++, cur_output = resolv_conf_cases[i].output) {
    glob_dict = g_variant_dict_new(NULL);
    if (resolv_conf_cases[i].options[0] != NULL) {
      g_variant_dict_insert(glob_dict, "options", "^as", resolv_conf_cases[i].options);
    }
    if (resolv_conf_cases[i].searches[0] != NULL) {
      g_variant_dict_insert(glob_dict, "searches", "^as", resolv_conf_cases[i].searches);
    }

    resolvconf_content = get_resolv_conf_string(glob_dict, devnull);
    ck_assert(!strcmp(resolvconf_content->str, resolv_conf_cases[i].output));
    g_variant_dict_unref(glob_dict);
    g_string_free(resolvconf_content, 1);
  }
  fclose(devnull);
}
END_TEST

typedef struct {
  const char *name;
  const gchar *servers[4];
} domain_servers_pair;

typedef struct {
  const domain_servers_pair domains[4];
  const char *output;
} unbound_conf_tuple;

static unbound_conf_tuple unbound_conf_cases[] = {
    {{{"*", {"8.8.8.8", "9.9.9.9", NULL}}, {0}},
     "server:\n\tmodule-config: \"ipsecmod iterator\"\n\tinterface: "
     "127.0.0.1\n\tdo-not-query-address: 127.0.0.1/8\n\ttls-cert-bundle: "
     "/etc/pki/ca-trust/extracted/pem/"
     "tls-ca-bundle.pem\nforward-zone:\n\tname: "
     "\".\"\n\tforward-addr: 8.8.8.8\n\tforward-addr: 9.9.9.9\n"},
    {{{"*", {"dns+tls://8.8.8.8", "dns+tls://9.9.9.9:55#example.org", NULL}}, {0}},
     "server:\n\tmodule-config: \"ipsecmod iterator\"\n\tinterface: "
     "127.0.0.1\n\tdo-not-query-address: 127.0.0.1/8\n\ttls-cert-bundle: "
     "/etc/pki/ca-trust/extracted/pem/"
     "tls-ca-bundle.pem\nforward-zone:\n\tname: "
     "\".\"\n\tforward-addr: 8.8.8.8\n\tforward-addr: "
     "9.9.9.9@55#example.org\n\tforward-tls-upstream: yes\n"},
    {{{"*", {"dns+tls://8.8.8.8", "dns+udp://9.9.9.9", NULL}}, {0}}, NULL},
    {{{"*", {"dns+tls://[2001:db8::1]:55#example.org", NULL}}, {0}},
     "server:\n\tmodule-config: \"ipsecmod iterator\"\n\tinterface: "
     "127.0.0.1\n\tdo-not-query-address: 127.0.0.1/8\n\ttls-cert-bundle: "
     "/etc/pki/ca-trust/extracted/pem/"
     "tls-ca-bundle.pem\nforward-zone:\n\tname: "
     "\".\"\n\tforward-addr: "
     "2001:db8::1@55#example.org\n\tforward-tls-upstream: yes\n"},
    {{{"*", {"dns+tls://[2001:db8::1]:55#example.org", NULL}},
      {"example.net", {"dns+udp://8.8.8.8:66", NULL}},
      {0}},
     "server:\n\tmodule-config: \"ipsecmod iterator\"\n\tinterface: "
     "127.0.0.1\n\tdo-not-query-address: 127.0.0.1/8\n\ttls-cert-bundle: "
     "/etc/pki/ca-trust/extracted/pem/"
     "tls-ca-bundle.pem\nforward-zone:\n\tname: "
     "\".\"\n\tforward-addr: "
     "2001:db8::1@55#example.org\n\tforward-tls-upstream: "
     "yes\nforward-zone:\n\tname: \"example.net\"\n\tforward-addr: "
     "8.8.8.8@66\n"},
    {{{"example.net", {"dns+udp://8.8.8.8:66", NULL}}, {0}},
     "server:\n\tmodule-config: \"ipsecmod iterator\"\n\tinterface: "
     "127.0.0.1\n\tdo-not-query-address: 127.0.0.1/8\n\ttls-cert-bundle: "
     "/etc/pki/ca-trust/extracted/pem/"
     "tls-ca-bundle.pem\nforward-zone:\n\tname: "
     "\"example.net\"\n\tforward-addr: 8.8.8.8@66\nforward-zone:\n\tname: "
     "\".\"\n\tforward-addr: "
     "127.0.0.1\n"},
};

START_TEST(test_get_unbound_conf_string) {
  GVariantDict *glob_dict;
  GVariantDict *domain_dict;
  GVariantDict *servers_dict;
  GString *resolvconf_content;
  GVariant *variant_servers_dict;
  GVariant *variant_domain_dict;
  const char *cur_output;

  FILE *devnull = fopen("/dev/null", "w");

  // size of build-time calculation here, so we can use NULL as value to
  // indicate no output
  for (int i = 0; i < sizeof(unbound_conf_cases) / sizeof(unbound_conf_tuple); i++) {
    cur_output = unbound_conf_cases[i].output;
    glob_dict = g_variant_dict_new(NULL);
    domain_dict = g_variant_dict_new(NULL);

    for (int k = 0; unbound_conf_cases[i].domains[k].name != NULL; k++) {
      servers_dict = g_variant_dict_new(NULL);
      g_variant_dict_insert(servers_dict, "servers", "^as",
                            unbound_conf_cases[i].domains[k].servers);
      variant_servers_dict = g_variant_dict_end(servers_dict);
      g_variant_dict_insert_value(domain_dict, unbound_conf_cases[i].domains[k].name,
                                  variant_servers_dict);
      g_variant_dict_unref(servers_dict);
    }

    variant_domain_dict = g_variant_dict_end(domain_dict);
    g_variant_dict_insert_value(glob_dict, "domains", variant_domain_dict);
    resolvconf_content = get_unbound_conf_string(
        glob_dict, "/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem", devnull);
    if (cur_output != NULL) {
      ck_assert(!strcmp(resolvconf_content->str, cur_output));
      g_string_free(resolvconf_content, 1);
    } else {
      ck_assert(resolvconf_content == NULL);
    }
    g_variant_dict_unref(glob_dict);
    g_variant_dict_unref(domain_dict);
  }
  fclose(devnull);
}
END_TEST

Suite *nm_config_parsing_suite() {
  Suite *s;
  TCase *tc_core;

  s = suite_create("nm-config-parsing");
  tc_core = tcase_create("Core");

  tcase_add_test(tc_core, test_get_resolv_conf_string);
  tcase_add_test(tc_core, test_get_unbound_conf_string);
  suite_add_tcase(s, tc_core);
  return s;
}
