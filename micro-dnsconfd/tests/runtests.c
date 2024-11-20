#include <check.h>

#include "test-nm-config-parsing.h"
#include "test-uri-parsing.h"

int main(void) {
  int number_failed;
  SRunner *sr;

  sr = srunner_create(uri_parsing_suite());
  srunner_add_suite(sr, nm_config_parsing_suite());

  srunner_run_all(sr, CK_NORMAL);
  number_failed = srunner_ntests_failed(sr);
  srunner_free(sr);
  return (number_failed != 0);
}
