#include "../src/types/network_address.h"
#include "../src/types/server_uri.h"
#include <check.h>
#include <glib.h>
#include <stdio.h>
#include <stdlib.h>

// Helper to create a server
static server_uri_t *create_test_server(int priority, dns_protocol_t protocol, int dnssec) {
  server_uri_t *server = calloc(1, sizeof(server_uri_t));
  server->priority = priority;
  server->protocol = protocol;
  server->dnssec = dnssec;
  return server;
}

static void add_domain(server_uri_t *server, const char *domain) {
  server->routing_domains = g_list_append(server->routing_domains, strdup(domain));
}

static void add_network(server_uri_t *server, const char *ip_str, int prefix) {
  network_address_t *net = malloc(sizeof(network_address_t));
  char buf[128];
  snprintf(buf, sizeof(buf), "%s/%d", ip_str, prefix);
  network_address_t_from_string(buf, net);
  server->networks = g_list_append(server->networks, net);
}

START_TEST(test_protocol_from_nstring) {
  ck_assert_int_eq(protocol_from_nstring("dns+udp", 7), DNS_UDP);
  ck_assert_int_eq(protocol_from_nstring("dns+tcp", 7), DNS_TCP);
  ck_assert_int_eq(protocol_from_nstring("dns+tls", 7), DNS_TLS);
  ck_assert_int_eq(protocol_from_nstring("unknown", 7), DNS_PROTOCOLS_END);
  ck_assert_int_eq(protocol_from_nstring("dns+udp", 6), DNS_PROTOCOLS_END);
}
END_TEST

START_TEST(test_dns_protocol_t_to_string) {
  ck_assert_str_eq(dns_protocol_t_to_string(DNS_UDP), "dns+udp");
  ck_assert_str_eq(dns_protocol_t_to_string(DNS_TCP), "dns+tcp");
  ck_assert_str_eq(dns_protocol_t_to_string(DNS_TLS), "dns+tls");
  ck_assert_str_eq(dns_protocol_t_to_string(DNS_PROTOCOLS_END), "unknown");
}
END_TEST

START_TEST(test_server_uri_init_from_string_valid) {
  server_uri_t *uri = calloc(1, sizeof(server_uri_t));
  int ret = server_uri_t_init_from_string("dns+udp://127.0.0.1:53", uri);
  ck_assert_int_eq(ret, 0);
  ck_assert_int_eq(uri->protocol, DNS_UDP);

  struct sockaddr_in *s4 = (struct sockaddr_in *)&uri->address;
  ck_assert_int_eq(s4->sin_family, AF_INET);
  ck_assert_int_eq(ntohs(s4->sin_port), 53);

  server_uri_t_destroy(uri);
}
END_TEST

START_TEST(test_server_uri_init_from_string_invalid) {
  server_uri_t *uri = calloc(1, sizeof(server_uri_t));
  int ret = server_uri_t_init_from_string("invalid_uri", uri);
  ck_assert_int_eq(ret, -1);
  server_uri_t_destroy(uri);
}
END_TEST

START_TEST(test_server_list_to_hash_table_basic) {
  GList *servers = NULL;
  server_uri_t *s1 = create_test_server(10, DNS_UDP, 1);
  add_domain(s1, "example.com");
  add_domain(s1, "test.com");
  servers = g_list_append(servers, s1);

  GHashTable *ht = server_list_to_hash_table(servers);
  ck_assert_ptr_ne(ht, NULL);
  ck_assert_int_eq(g_hash_table_size(ht), 2);

  GList *l1 = g_hash_table_lookup(ht, "example.com");
  ck_assert_ptr_ne(l1, NULL);
  ck_assert_int_eq(g_list_length(l1), 1);
  ck_assert_ptr_eq(l1->data, s1);

  GList *l2 = g_hash_table_lookup(ht, "test.com");
  ck_assert_ptr_ne(l2, NULL);
  ck_assert_int_eq(g_list_length(l2), 1);
  ck_assert_ptr_eq(l2->data, s1);

  g_hash_table_destroy(ht);
  g_list_free_full(servers, server_uri_t_destroy);
}
END_TEST

START_TEST(test_server_list_to_hash_table_sorting) {
  GList *servers = NULL;
  server_uri_t *s1 = create_test_server(10, DNS_UDP, 1); // Low priority
  add_domain(s1, "example.com");

  server_uri_t *s2 = create_test_server(20, DNS_UDP, 1); // High priority
  add_domain(s2, "example.com");

  server_uri_t *s3 = create_test_server(20, DNS_TLS, 1); // High priority, Better protocol
  add_domain(s3, "example.com");

  servers = g_list_append(servers, s1);
  servers = g_list_append(servers, s2);
  servers = g_list_append(servers, s3);

  GHashTable *ht = server_list_to_hash_table(servers);
  ck_assert_ptr_ne(ht, NULL);

  GList *l = g_hash_table_lookup(ht, "example.com");
  ck_assert_int_eq(g_list_length(l), 3);

  // Expected order: s3 (20, TLS), s2 (20, UDP), s1 (10, UDP)
  // compare_servers: b->priority - a->priority.
  // If equal, b->protocol - a->protocol.
  // TLS is 2, UDP is 0.

  ck_assert_ptr_eq(l->data, s3);
  ck_assert_ptr_eq(l->next->data, s2);
  ck_assert_ptr_eq(l->next->next->data, s1);

  g_hash_table_destroy(ht);
  g_list_free_full(servers, server_uri_t_destroy);
}
END_TEST

START_TEST(test_server_list_to_hash_table_networks) {
  GList *servers = NULL;
  server_uri_t *s1 = create_test_server(10, DNS_UDP, 1);
  add_network(s1, "192.168.1.0", 24); // 1.168.192.in-addr.arpa
  servers = g_list_append(servers, s1);

  GHashTable *ht = server_list_to_hash_table(servers);
  ck_assert_ptr_ne(ht, NULL);

  // 192.168.1.0/24 -> 24 bits = 3 bytes. 192.168.1.
  // Reverse: 1.168.192.in-addr.arpa

  GList *l = g_hash_table_lookup(ht, "1.168.192.in-addr.arpa");
  ck_assert_ptr_ne(l, NULL);
  ck_assert_ptr_eq(l->data, s1);

  g_hash_table_destroy(ht);
  g_list_free_full(servers, server_uri_t_destroy);
}
END_TEST

Suite *server_uri_suite(void) {
  Suite *s;
  TCase *tc_core;

  s = suite_create("Server URI");

  /* Core test case */
  tc_core = tcase_create("Core");

  tcase_add_test(tc_core, test_protocol_from_nstring);
  tcase_add_test(tc_core, test_dns_protocol_t_to_string);
  tcase_add_test(tc_core, test_server_uri_init_from_string_valid);
  tcase_add_test(tc_core, test_server_uri_init_from_string_invalid);
  tcase_add_test(tc_core, test_server_list_to_hash_table_basic);
  tcase_add_test(tc_core, test_server_list_to_hash_table_sorting);
  tcase_add_test(tc_core, test_server_list_to_hash_table_networks);

  suite_add_tcase(s, tc_core);

  return s;
}

int main(void) {
  int number_failed;
  Suite *s;
  SRunner *sr;

  s = server_uri_suite();
  sr = srunner_create(s);

  srunner_run_all(sr, CK_NORMAL);
  number_failed = srunner_ntests_failed(sr);
  srunner_free(sr);
  return (number_failed == 0) ? EXIT_SUCCESS : EXIT_FAILURE;
}
