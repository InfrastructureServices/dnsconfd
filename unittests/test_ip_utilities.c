#include "../src/ip_utilities.h"
#include <arpa/inet.h>
#include <check.h>
#include <stdio.h>
#include <stdlib.h>

START_TEST(test_parse_ip_str_ipv4) {
  struct sockaddr_storage addr;
  int ret = parse_ip_str("127.0.0.1", &addr);
  ck_assert_int_eq(ret, 0);
  ck_assert_int_eq(addr.ss_family, AF_INET);

  struct sockaddr_in *s4 = (struct sockaddr_in *)&addr;
  char buffer[INET_ADDRSTRLEN];
  inet_ntop(AF_INET, &s4->sin_addr, buffer, INET_ADDRSTRLEN);
  ck_assert_str_eq(buffer, "127.0.0.1");
}
END_TEST

START_TEST(test_parse_ip_str_ipv6) {
  struct sockaddr_storage addr;
  int ret = parse_ip_str("::1", &addr);
  ck_assert_int_eq(ret, 0);
  ck_assert_int_eq(addr.ss_family, AF_INET6);

  struct sockaddr_in6 *s6 = (struct sockaddr_in6 *)&addr;
  char buffer[INET6_ADDRSTRLEN];
  inet_ntop(AF_INET6, &s6->sin6_addr, buffer, INET6_ADDRSTRLEN);
  ck_assert_str_eq(buffer, "::1");
}
END_TEST

START_TEST(test_parse_ip_str_invalid) {
  struct sockaddr_storage addr;
  int ret = parse_ip_str("invalid", &addr);
  ck_assert_int_eq(ret, -1);
}
END_TEST

START_TEST(test_ip_to_str_ipv4) {
  struct sockaddr_storage addr;
  struct sockaddr_in *s4 = (struct sockaddr_in *)&addr;
  s4->sin_family = AF_INET;
  inet_pton(AF_INET, "192.168.1.1", &s4->sin_addr);

  char buffer[INET6_ADDRSTRLEN];
  int ret = ip_to_str(&addr, buffer);
  ck_assert_int_eq(ret, 0);
  ck_assert_str_eq(buffer, "192.168.1.1");
}
END_TEST

START_TEST(test_are_ips_equal) {
  struct sockaddr_storage addr1, addr2;
  parse_ip_str("127.0.0.1", &addr1);
  parse_ip_str("127.0.0.1", &addr2);
  ck_assert(are_ips_equal(&addr1, &addr2));

  parse_ip_str("127.0.0.2", &addr2);
  ck_assert(!are_ips_equal(&addr1, &addr2));
}
END_TEST

Suite *ip_utilities_suite(void) {
  Suite *s;
  TCase *tc_core;

  s = suite_create("IP Utilities");

  /* Core test case */
  tc_core = tcase_create("Core");

  tcase_add_test(tc_core, test_parse_ip_str_ipv4);
  tcase_add_test(tc_core, test_parse_ip_str_ipv6);
  tcase_add_test(tc_core, test_parse_ip_str_invalid);
  tcase_add_test(tc_core, test_ip_to_str_ipv4);
  tcase_add_test(tc_core, test_are_ips_equal);

  suite_add_tcase(s, tc_core);

  return s;
}

int main(void) {
  int number_failed;
  Suite *s;
  SRunner *sr;

  s = ip_utilities_suite();
  sr = srunner_create(s);

  srunner_run_all(sr, CK_NORMAL);
  number_failed = srunner_ntests_failed(sr);
  srunner_free(sr);
  return (number_failed == 0) ? EXIT_SUCCESS : EXIT_FAILURE;
}
