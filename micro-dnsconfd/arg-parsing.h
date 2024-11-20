#include <argp.h>

#ifndef ARG_PARSING_H
#define ARG_PARSING_H

typedef struct arguments {
  char *resolvconf;
  char *unboundconf;
  unsigned char no_error_code;
} arguments;

error_t parse_args(int argc, char *argv[], arguments *args);

#endif
