#include "file-utilities.h"

#include <sys/stat.h>

const char *get_best_ca_bundle() {
  struct stat ca_stat;

  // if dns specific bundle does not exist or is not a regular file
  // then use the global one
  if (stat("/etc/pki/dns/extracted/pem/tls-ca-bundle.pem", &ca_stat) || !S_ISREG(ca_stat.st_mode)) {
    return "/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem";
  }
  return "/etc/pki/dns/extracted/pem/tls-ca-bundle.pem";
}
