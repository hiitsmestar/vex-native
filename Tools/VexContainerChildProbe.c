// VexNative v0.13.6 read-only direct-child enumerator.
// Technique reference: forcequitOS/bad_query + jailbreakdotparty/Erosion.
// Read-only only: returns path strings; no create/write/rename/delete APIs.

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mount.h>
#include <sys/fsgetpath.h>

char *vex_bad_query_list_children(const char *path, int64_t max_inode) {
    if (path == NULL || path[0] != '/' || max_inode < 1) return NULL;

    struct statfs sfs;
    if (statfs(path, &sfs) != 0) {
        if (statfs("/private/var", &sfs) != 0 && statfs("/var", &sfs) != 0) return NULL;
    }

    fsid_t fsid = sfs.f_fsid;
    size_t cap = 65536, length = 0;
    const size_t path_length = strlen(path);
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
            while (length + need > cap) cap *= 2;
            char *tmp = realloc(out, cap);
            if (!tmp) { free(out); return NULL; }
            out = tmp;
        }
        length += snprintf(out + length, cap - length, "%s\n", p);
    }
    return out;
}

void vex_bad_query_free_string(char *value) {
    free(value);
}
