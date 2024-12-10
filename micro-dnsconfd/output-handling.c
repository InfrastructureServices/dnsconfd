#include "output-handling.h"

#include <gio/gio.h>
#include <stdio.h>

static unsigned char write_to_file(GString *content, char *path) {
  unsigned char print_rc;
  unsigned char close_rc;
  FILE *opened_file = fopen(path, "w");
  if (!opened_file) {
    fprintf(stderr, "Failed to open %s errno %d", path, errno);
    return 1;
  }

  print_rc = (fprintf(opened_file, "%s", content->str) != strlen(content->str));
  close_rc = fclose(opened_file);

  if (print_rc) {
    fprintf(stderr, "Failed to write to %s", path);
    return 1;
  } else if (close_rc) {
    fprintf(stderr, "Failed to close %s", path);
    return 1;
  }
  return 0;
}

unsigned char handle_output(char *filename, GString *content) {
  if (!filename) {
    fprintf(stdout, "%s", content->str);
    return 0;
  }
  return write_to_file(content, filename);
}
