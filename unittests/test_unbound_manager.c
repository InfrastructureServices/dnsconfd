#include <check.h>
#include <stdlib.h>
#include <stdio.h>
#include <glib.h>

// Include the source file to test static functions
// We need to define some things that might be missing or mocked if necessary,
// but since we link against the dependencies, it should be fine.
#include "../src/dns_managers/unbound_manager.c"

// Helper to create a server_uri_t
static server_uri_t* create_server(int priority, dns_protocol_t protocol, int dnssec, const char* interface) {
    server_uri_t* server = calloc(1, sizeof(server_uri_t));
    server->priority = priority;
    server->protocol = protocol;
    server->dnssec = dnssec;
    if (interface) {
        strncpy(server->interface, interface, IFNAMSIZ - 1);
    }
    return server;
}

START_TEST(test_get_used_servers_priority)
{
    GList* servers = NULL;
    server_uri_t* s1 = create_server(100, DNS_UDP, 1, NULL);
    server_uri_t* s2 = create_server(100, DNS_UDP, 1, NULL);
    server_uri_t* s3 = create_server(50, DNS_UDP, 1, NULL);

    servers = g_list_append(servers, s1);
    servers = g_list_append(servers, s2);
    servers = g_list_append(servers, s3);

    GList* result = get_used_servers(servers, MODE_BACKUP, ".");
    
    // Should contain s1 and s2 (priority 100), but not s3 (priority 50)
    ck_assert_int_eq(g_list_length(result), 2);
    
    // Verify contents (order might be reversed due to prepend)
    int found_s1 = 0, found_s2 = 0;
    for (GList* l = result; l != NULL; l = l->next) {
        if (l->data == s1) found_s1 = 1;
        if (l->data == s2) found_s2 = 1;
        ck_assert_ptr_ne(l->data, s3);
    }
    ck_assert(found_s1 && found_s2);

    g_list_free(result);
    g_list_free_full(servers, server_uri_t_destroy);
}
END_TEST

START_TEST(test_get_used_servers_protocol)
{
    GList* servers = NULL;
    server_uri_t* s1 = create_server(100, DNS_TLS, 1, NULL);
    server_uri_t* s2 = create_server(100, DNS_UDP, 1, NULL);

    servers = g_list_append(servers, s1);
    servers = g_list_append(servers, s2);

    GList* result = get_used_servers(servers, MODE_BACKUP, ".");
    
    // Should contain s1 (TLS > UDP)
    ck_assert_int_eq(g_list_length(result), 1);
    ck_assert_ptr_eq(result->data, s1);

    g_list_free(result);
    g_list_free_full(servers, server_uri_t_destroy);
}
END_TEST

START_TEST(test_get_used_servers_dnssec)
{
    GList* servers = NULL;
    server_uri_t* s1 = create_server(100, DNS_UDP, 1, NULL);
    server_uri_t* s2 = create_server(100, DNS_UDP, 0, NULL);

    servers = g_list_append(servers, s1);
    servers = g_list_append(servers, s2);

    GList* result = get_used_servers(servers, MODE_BACKUP, ".");
    
    // Should contain s1 (dnssec mismatch breaks the loop)
    ck_assert_int_eq(g_list_length(result), 1);
    ck_assert_ptr_eq(result->data, s1);

    g_list_free(result);
    g_list_free_full(servers, server_uri_t_destroy);
}
END_TEST

START_TEST(test_get_used_servers_interface_backup)
{
    GList* servers = NULL;
    server_uri_t* s1 = create_server(100, DNS_UDP, 1, "eth0");

    servers = g_list_append(servers, s1);

    GList* result = get_used_servers(servers, MODE_BACKUP, ".");
    
    // MODE_BACKUP allows interface
    ck_assert_int_eq(g_list_length(result), 1);
    ck_assert_ptr_eq(result->data, s1);

    g_list_free(result);
    g_list_free_full(servers, server_uri_t_destroy);
}
END_TEST

START_TEST(test_get_used_servers_interface_prefer_root)
{
    GList* servers = NULL;
    server_uri_t* s1 = create_server(100, DNS_UDP, 1, "eth0");

    servers = g_list_append(servers, s1);

    GList* result = get_used_servers(servers, MODE_PREFER, ".");
    
    // MODE_PREFER on root domain skips interface
    ck_assert_int_eq(g_list_length(result), 0);

    g_list_free(result);
    g_list_free_full(servers, server_uri_t_destroy);
}
END_TEST

START_TEST(test_get_used_servers_interface_prefer_nonroot)
{
    GList* servers = NULL;
    server_uri_t* s1 = create_server(100, DNS_UDP, 1, "eth0");

    servers = g_list_append(servers, s1);

    GList* result = get_used_servers(servers, MODE_PREFER, "example.com");
    
    // MODE_PREFER on non-root domain allows interface
    ck_assert_int_eq(g_list_length(result), 1);
    ck_assert_ptr_eq(result->data, s1);

    g_list_free(result);
    g_list_free_full(servers, server_uri_t_destroy);
}
END_TEST

START_TEST(test_get_used_servers_interface_exclusive)
{
    GList* servers = NULL;
    server_uri_t* s1 = create_server(100, DNS_UDP, 1, "eth0");

    servers = g_list_append(servers, s1);

    GList* result = get_used_servers(servers, MODE_EXCLUSIVE, ".");
    
    // MODE_EXCLUSIVE skips interface regardless of domain
    ck_assert_int_eq(g_list_length(result), 0);

    g_list_free(result);
    g_list_free_full(servers, server_uri_t_destroy);
}
END_TEST

START_TEST(test_get_used_servers_interface_exclusive_nonroot)
{
    GList* servers = NULL;
    server_uri_t* s1 = create_server(100, DNS_UDP, 1, "eth0");

    servers = g_list_append(servers, s1);

    GList* result = get_used_servers(servers, MODE_EXCLUSIVE, "example.com");
    
    // MODE_EXCLUSIVE skips interface regardless of domain
    ck_assert_int_eq(g_list_length(result), 0);

    g_list_free(result);
    g_list_free_full(servers, server_uri_t_destroy);
}
END_TEST

START_TEST(test_get_used_servers_mixed)
{
    GList* servers = NULL;
    server_uri_t* s1 = create_server(100, DNS_UDP, 1, NULL); // Global
    server_uri_t* s2 = create_server(100, DNS_UDP, 1, "eth0"); // Interface

    servers = g_list_append(servers, s1);
    servers = g_list_append(servers, s2);

    // Case 1: MODE_PREFER, root domain -> should get s1 only
    GList* result = get_used_servers(servers, MODE_PREFER, ".");
    ck_assert_int_eq(g_list_length(result), 1);
    ck_assert_ptr_eq(result->data, s1);
    g_list_free(result);

    // Case 2: MODE_BACKUP, root domain -> should get both
    result = get_used_servers(servers, MODE_BACKUP, ".");
    ck_assert_int_eq(g_list_length(result), 2);
    g_list_free(result);

    // Case 3: MODE_EXCLUSIVE, non-root -> should get s1 only
    result = get_used_servers(servers, MODE_EXCLUSIVE, "example.com");
    ck_assert_int_eq(g_list_length(result), 1);
    ck_assert_ptr_eq(result->data, s1);
    g_list_free(result);

    g_list_free_full(servers, server_uri_t_destroy);
}
END_TEST

Suite * unbound_manager_suite(void)
{
    Suite *s;
    TCase *tc_core;

    s = suite_create("Unbound Manager");

    /* Core test case */
    tc_core = tcase_create("Core");

    tcase_add_test(tc_core, test_get_used_servers_priority);
    tcase_add_test(tc_core, test_get_used_servers_protocol);
    tcase_add_test(tc_core, test_get_used_servers_dnssec);
    tcase_add_test(tc_core, test_get_used_servers_interface_backup);
    tcase_add_test(tc_core, test_get_used_servers_interface_prefer_root);
    tcase_add_test(tc_core, test_get_used_servers_interface_prefer_nonroot);
    tcase_add_test(tc_core, test_get_used_servers_interface_exclusive);
    tcase_add_test(tc_core, test_get_used_servers_interface_exclusive_nonroot);
    tcase_add_test(tc_core, test_get_used_servers_mixed);

    suite_add_tcase(s, tc_core);

    return s;
}

int main(void)
{
    int number_failed;
    Suite *s;
    SRunner *sr;

    s = unbound_manager_suite();
    sr = srunner_create(s);

    srunner_run_all(sr, CK_NORMAL);
    number_failed = srunner_ntests_failed(sr);
    srunner_free(sr);
    return (number_failed == 0) ? EXIT_SUCCESS : EXIT_FAILURE;
}
