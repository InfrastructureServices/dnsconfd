cmake_minimum_required(VERSION 3.10)
project(micro-dnsconfd LANGUAGES C)
enable_testing()

find_package(PkgConfig REQUIRED)

pkg_check_modules(glib-2.0 REQUIRED IMPORTED_TARGET glib-2.0)
pkg_check_modules(gio-2.0 IMPORTED_TARGET REQUIRED gio-2.0)
pkg_check_modules(libcurl REQUIRED IMPORTED_TARGET libcurl)
pkg_check_modules(check REQUIRED IMPORTED_TARGET check)

set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -g -Wall")

add_executable(
micro-dnsconfd
micro-dnsconfd.c
uri-parsing.c
uri-parsing.h
dbus-handling.c
dbus-handling.h
arg-parsing.c
arg-parsing.h
output-handling.c
output-handling.h
nm-config-parsing.c
nm-config-parsing.h
file-utilities.c
file-utilities.h
)
target_link_libraries(micro-dnsconfd PUBLIC PkgConfig::glib-2.0 PkgConfig::gio-2.0 PkgConfig::libcurl)
target_include_directories(micro-dnsconfd PUBLIC PkgConfig::glib-2.0 PkgConfig::gio-2.0 PkgConfig::libcurl)

add_executable(
runtests
tests/runtests.c
tests/test-uri-parsing.c
tests/test-uri-parsing.h
tests/test-nm-config-parsing.c
tests/test-nm-config-parsing.h
uri-parsing.c
uri-parsing.h
dbus-handling.c
dbus-handling.h
arg-parsing.c
arg-parsing.h
output-handling.c
output-handling.h
nm-config-parsing.c
nm-config-parsing.h
file-utilities.c
file-utilities.h
)
target_link_libraries(runtests PkgConfig::check PkgConfig::gio-2.0 PkgConfig::libcurl)
target_include_directories(runtests PUBLIC PkgConfig::check PkgConfig::gio-2.0 PkgConfig::libcurl ${CMAKE_SOURCE_DIR})
add_test(NAME runtests
         COMMAND runtests)

install(TARGETS micro-dnsconfd RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR})
