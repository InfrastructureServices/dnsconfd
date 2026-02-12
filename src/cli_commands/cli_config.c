#include "cli_config.h"

#include <errno.h>
#include <glib.h>
#include <pwd.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

#include "log_utilities.h"

#define NM_CONFIG_PATH "/etc/NetworkManager/conf.d/dnsconfd.conf"
#define NM_CONFIG_CONTENT "[main]\ndns=dnsconfd\n"

static int reload_network_manager() {
  gint exit_status;
  gboolean success;
  GError* error = NULL;
  char* argv[] = {"systemctl", "reload", "NetworkManager", NULL};

  success = g_spawn_sync(NULL, argv, NULL, G_SPAWN_SEARCH_PATH, NULL, NULL, NULL, NULL,
                         &exit_status, &error);

  if (!success) {
    fprintf(stderr, "Failed to execute systemctl reload NetworkManager: %s\n", error->message);
    g_error_free(error);
    return EXIT_COMMAND_FAILURE;
  }

  if (WIFEXITED(exit_status) && WEXITSTATUS(exit_status) != 0) {
    fprintf(stderr, "systemctl reload NetworkManager failed with exit code %d\n",
            WEXITSTATUS(exit_status));
    return EXIT_COMMAND_FAILURE;
  }
  if (WIFSIGNALED(exit_status)) {
    fprintf(stderr, "systemctl reload NetworkManager terminated by signal %d\n",
            WTERMSIG(exit_status));
    return EXIT_COMMAND_FAILURE;
  }
  return EXIT_OK;
}

static int do_nm_enable() {
  FILE* fp = fopen(NM_CONFIG_PATH, "w");
  if (!fp) {
    fprintf(stderr, "Failed to open %s for writing: %s\n", NM_CONFIG_PATH, strerror(errno));
    return EXIT_COMMAND_FAILURE;
  }
  if (fprintf(fp, NM_CONFIG_CONTENT) < 0) {
    fprintf(stderr, "Failed to write to %s: %s\n", NM_CONFIG_PATH, strerror(errno));
    fclose(fp);
    return EXIT_COMMAND_FAILURE;
  }
  fclose(fp);
  return reload_network_manager();
}

static int do_nm_disable() {
  struct stat st;
  FILE* fp;
  if (stat(NM_CONFIG_PATH, &st) == 0) {
    fp = fopen(NM_CONFIG_PATH, "w");
    if (!fp) {
      fprintf(stderr, "Failed to open %s for clearing: %s\n", NM_CONFIG_PATH, strerror(errno));
      return EXIT_COMMAND_FAILURE;
    }
    fclose(fp);
  } else if (errno != ENOENT) {
    fprintf(stderr, "Failed to stat %s: %s\n", NM_CONFIG_PATH, strerror(errno));
    return EXIT_COMMAND_FAILURE;
  }
  return reload_network_manager();
}

static int do_take_resolvconf(const char* path) {
  struct stat st;
  struct passwd* pwd;
  FILE* fp;

  if (lstat(path, &st) == 0) {
    if (S_ISLNK(st.st_mode)) {
      if (unlink(path) != 0) {
        fprintf(stderr, "Failed to remove symlink %s: %s\n", path, strerror(errno));
        return EXIT_COMMAND_FAILURE;
      }
    }
  } else {
    if (errno != ENOENT) {
      fprintf(stderr, "Failed to stat %s: %s\n", path, strerror(errno));
      return EXIT_COMMAND_FAILURE;
    }
  }

  // Ensure file exists
  fp = fopen(path, "a");
  if (!fp) {
    fprintf(stderr, "Failed to open/create %s: %s\n", path, strerror(errno));
    return EXIT_COMMAND_FAILURE;
  }
  fclose(fp);

  pwd = getpwnam("dnsconfd");
  if (!pwd) {
    fprintf(stderr, "User 'dnsconfd' not found\n");
    return EXIT_COMMAND_FAILURE;
  }

  if (chown(path, pwd->pw_uid, st.st_gid) != 0) {
    fprintf(stderr, "Failed to change ownership of %s to dnsconfd: %s\n", path, strerror(errno));
    return EXIT_COMMAND_FAILURE;
  }
  return EXIT_OK;
}

static int do_return_resolvconf(const char* path) {
  if (chown(path, 0, 0) != 0) {  // 0 is root
    fprintf(stderr, "Failed to change ownership of %s to root: %s\n", path, strerror(errno));
    return EXIT_COMMAND_FAILURE;
  }
  return EXIT_OK;
}

int cli_config_command(dnsconfd_config_t* config) {
  int ret = 0;
  config_action_t action = config->command_options.config_options.action;
  const char* resolv_conf = config->resolv_conf_path;

  switch (action) {
    case CONFIG_ACTION_NM_ENABLE:
      ret = do_nm_enable();
      break;
    case CONFIG_ACTION_NM_DISABLE:
      ret = do_nm_disable();
      break;
    case CONFIG_ACTION_TAKE_RESOLVCONF:
      ret = do_take_resolvconf(resolv_conf);
      break;
    case CONFIG_ACTION_RETURN_RESOLVCONF:
      ret = do_return_resolvconf(resolv_conf);
      break;
    case CONFIG_ACTION_INSTALL:
      ret = do_nm_enable();
      if (ret == EXIT_OK) {
        ret = do_take_resolvconf(resolv_conf);
      }
      break;
    case CONFIG_ACTION_UNINSTALL:
      ret = do_nm_disable();
      if (ret == EXIT_OK) {
        ret = do_return_resolvconf(resolv_conf);
      }
      break;
    default:
      fprintf(stderr, "Unknown config action\n");
      ret = EXIT_BAD_ARGUMENTS;
      break;
  }
  return ret;
}
