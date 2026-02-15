project('dnsconfd', 'c', version: '2.0.0')

executable(
    'dnsconfd',
    'src/main.c',
    'src/configuration_parsing/global_options.c',
    'src/configuration_parsing/status_command.c',
    'src/configuration_parsing/update_command.c',
    'src/configuration_parsing/config_command.c',
    'src/configuration_parsing/reload_command.c',
    'src/configuration_parsing/config_file.c',
    'src/configuration_parsing/environment_config.c',
    'src/configuration_parsing/config_utils.c',
    'src/cli_commands/cli_config.c',
    'src/cli_commands/cli_update.c',
    'src/cli_commands/cli_common.c',
    'src/types/network_address.c',
    'src/types/server_uri.c',
    'src/ip_utilities.c',
    'src/log_utilities.c',
    'src/dbus_server.c',
    'src/service_management.c',
    'src/dns_managers/unbound_manager.c',
    'src/fsm/fsm.c',
    include_directories: include_directories('src'),
    dependencies: [
        dependency('liburiparser'),
        dependency('jansson'),
        dependency('yaml-0.1'),
        dependency('glib-2.0'),
        dependency('gio-2.0'),
        dependency('libsystemd'),
        dependency('libidn2'),
    ],
    install : true
)

subdir('unittests')
