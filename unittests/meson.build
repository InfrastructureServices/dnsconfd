check_dep = dependency('check')

test_ip_utilities = executable('test_ip_utilities',
    'test_ip_utilities.c',
    '../src/ip_utilities.c',
    dependencies: [check_dep],
    include_directories: include_directories('../src')
)
test('test_ip_utilities', test_ip_utilities)

test_server_uri = executable('test_server_uri',
    'test_server_uri.c',
    '../src/types/server_uri.c',
    '../src/ip_utilities.c',
    '../src/types/network_address.c',
    dependencies: [
        check_dep,
        dependency('glib-2.0'),
        dependency('gio-2.0'),
        dependency('jansson'),
        dependency('liburiparser'),
    ],
    include_directories: include_directories('../src')
)
test('test_server_uri', test_server_uri)

test_unbound_manager = executable('test_unbound_manager',
    'test_unbound_manager.c',
    '../src/types/server_uri.c',
    '../src/ip_utilities.c',
    '../src/types/network_address.c',
    dependencies: [
        check_dep,
        dependency('glib-2.0'),
        dependency('gio-2.0'),
        dependency('jansson'),
        dependency('liburiparser'),
    ],
    include_directories: include_directories('../src')
)
test('test_unbound_manager', test_unbound_manager)
