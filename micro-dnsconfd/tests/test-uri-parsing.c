#include "test-uri-parsing.h"

#include <check.h>
#include <stdio.h>

#include "uri-parsing.h"

typedef struct {
  char *input;
  char *output;
  unsigned char is_domain_tls;
  unsigned char return_code;
} ioTuple;

static ioTuple io_tuples[] = {
    {"8.8.8.8", "\tforward-addr: 8.8.8.8\n", 0, 0},
    {"dns+tls://8.8.8.8", "\tforward-addr: 8.8.8.8\n", 1, 0},
    {"dns+tls://8.8.8.8:55", "\tforward-addr: 8.8.8.8@55\n", 1, 0},
    {"dns+tls://8.8.8.8:55#example.org", "\tforward-addr: 8.8.8.8@55#example.org\n", 1, 0},
    {"dns+udp://8.8.8.8", "\tforward-addr: 8.8.8.8\n", 0, 0},
    {"dns+udp://8.8.8.8:55", "\tforward-addr: 8.8.8.8@55\n", 0, 0},
    {"dns+udp://8.8.8.8#example.org", "\tforward-addr: 8.8.8.8#example.org\n", 0, 0},
    {"dns+tls://[::1]", "\tforward-addr: ::1\n", 1, 0},
    {"dns+tls://[::1]:55", "\tforward-addr: ::1@55\n", 1, 0},
    {"dns+tls://[::1]:55#example.org", "\tforward-addr: ::1@55#example.org\n", 1, 0},
    {"dns+udp://[::1]", "\tforward-addr: ::1\n", 0, 0},
    {"dns+udp://[::1]:55", "\tforward-addr: ::1@55\n", 0, 0},
    {"dns+udp://[::1]#example.org", "\tforward-addr: ::1#example.org\n", 0, 0},
    {"500.8.8.8", NULL, 0, 1},
    {"dns+whatever://8.8.8.8", NULL, 1, 1},
    {"dns+tls://[8.8.8.8", NULL, 1, 1},
    {"dns+tls://[", NULL, 1, 1},
    {0}};

START_TEST(test_parsing) {
  GString *config_string = g_string_new(NULL);
  unsigned char domain_tls;
  ioTuple *cur_tuple = &io_tuples[0];

  FILE *dev_null = fopen("/dev/null", "w");

  for (int i = 0; cur_tuple->input != 0; i++, cur_tuple = &io_tuples[i]) {
    domain_tls = 0;
    ck_assert(transform_server_string(cur_tuple->input, &domain_tls, config_string, dev_null) ==
              cur_tuple->return_code);
    if (!cur_tuple->return_code) {
      ck_assert(domain_tls == cur_tuple->is_domain_tls);
      ck_assert(strcmp(config_string->str, cur_tuple->output) == 0);
    }
    g_string_truncate(config_string, 0);
  }
  g_string_free(config_string, 1);
  fclose(dev_null);
}
END_TEST

Suite *uri_parsing_suite() {
  Suite *s;
  TCase *tc_core;

  s = suite_create("uri-parsing");
  tc_core = tcase_create("Core");

  tcase_add_test(tc_core, test_parsing);
  suite_add_tcase(s, tc_core);
  return s;
}
