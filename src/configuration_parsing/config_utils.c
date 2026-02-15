#include "config_utils.h"
#include <string.h>

unsigned char parse_boolean(const char *str) {
  return strcmp(str, "yes") == 0 || strcmp(str, "1") == 0 ? CONFIG_BOOLEAN_TRUE
                                                          : CONFIG_BOOLEAN_FALSE;
}
