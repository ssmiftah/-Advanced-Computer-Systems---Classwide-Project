// Shared helpers for the Project 2 memory benchmarks (header-only).
#ifndef P2_COMMON_H
#define P2_COMMON_H
#pragma GCC diagnostic ignored "-Wunused-function"
#define _GNU_SOURCE
#include <fcntl.h>
#include <linux/perf_event.h>
#include <pthread.h>
#include <sched.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/syscall.h>
#include <time.h>
#include <unistd.h>

#define HUGE_2M ((size_t)2 << 20)

static inline double now_ns(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC_RAW, &ts);
    return ts.tv_sec * 1e9 + ts.tv_nsec;
}

// xorshift64*: deterministic, cheap RNG (state passed explicitly -> thread safe).
static inline uint64_t xs64(uint64_t *s) {
    *s ^= *s >> 12; *s ^= *s << 25; *s ^= *s >> 27;
    return *s * 2685821657736338717ULL;
}

// Parse a CPU list such as "4,5,6-7". "none" (or empty) -> 0 CPUs, meaning
// "do not pin" (used to demonstrate the unpinned-threads pitfall).
static int parse_cpus(const char *s, int *out, int max) {
    int n = 0;
    if (!s || !*s || strcmp(s, "none") == 0) return 0;
    char *copy = strdup(s), *save = NULL;
    for (char *tok = strtok_r(copy, ",", &save); tok; tok = strtok_r(NULL, ",", &save)) {
        int a, b;
        if (sscanf(tok, "%d-%d", &a, &b) == 2) {
            for (int c = a; c <= b && n < max; c++) out[n++] = c;
        } else if (n < max) {
            out[n++] = atoi(tok);
        }
    }
    free(copy);
    return n;
}

static void pin_cpu(int cpu) {
    if (cpu < 0) return;
    cpu_set_t set;
    CPU_ZERO(&set);
    CPU_SET(cpu, &set);
    if (sched_setaffinity(0, sizeof set, &set) != 0) perror("sched_setaffinity");
}

// mmap `len` bytes aligned to 2 MiB; thp!=0 -> MADV_HUGEPAGE else MADV_NOHUGEPAGE.
// Memory is NOT touched here (caller decides whether to pre-fault).
static void *alloc_pages(size_t len, int thp, size_t *maplen) {
    size_t ml = (len + HUGE_2M - 1) & ~(HUGE_2M - 1);
    char *raw = mmap(NULL, ml + HUGE_2M, PROT_READ | PROT_WRITE,
                     MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (raw == MAP_FAILED) { perror("mmap"); exit(1); }
    char *buf = (char *)(((uintptr_t)raw + HUGE_2M - 1) & ~(HUGE_2M - 1));
    madvise(buf, ml, thp ? MADV_HUGEPAGE : MADV_NOHUGEPAGE);
    if (maplen) *maplen = ml;
    return buf;
}

// Fraction of the VMAs overlapping [bufs[i], bufs[i]+lens[i]) that is backed by
// transparent huge pages, from /proc/self/smaps (AnonHugePages / Size). Call
// AFTER the buffers have been touched. Each VMA is counted once even if several
// of our buffers were merged into it. Returns -1 if smaps is unreadable.
static double thp_fraction(char **bufs, const size_t *lens, int n) {
    FILE *f = fopen("/proc/self/smaps", "r");
    if (!f) return -1;
    char line[512];
    int hit = 0;
    double huge_kb = 0, size_kb = 0;
    while (fgets(line, sizeof line, f)) {
        unsigned long lo, hi;
        if (sscanf(line, "%lx-%lx ", &lo, &hi) == 2 && strchr(line, '-') && line[0] != 'A') {
            hit = 0;
            for (int i = 0; i < n; i++)
                if (lo < (unsigned long)bufs[i] + lens[i] && hi > (unsigned long)bufs[i]) hit = 1;
        } else if (hit) {
            long kb;
            if (sscanf(line, "Size: %ld kB", &kb) == 1) size_kb += kb;
            else if (sscanf(line, "AnonHugePages: %ld kB", &kb) == 1) huge_kb += kb;
        }
    }
    fclose(f);
    return size_kb > 0 ? huge_kb / size_kb : -1;
}

// ---- perf stat --control support -------------------------------------------
// Run as: perf stat -D -1 --control fifo:CTL,ACK ... -- prog --ctl CTL --ack ACK
// The program then enables counting only around its timed region.
static int ctl_fd = -1, ack_fd = -1;
static void ctl_open(const char *ctl, const char *ack) {
    if (!ctl || !ack) return;
    ctl_fd = open(ctl, O_WRONLY);
    ack_fd = open(ack, O_RDONLY);
}
static void ctl_cmd(const char *cmd) {
    if (ctl_fd < 0) return;
    char b[32];
    if (write(ctl_fd, cmd, strlen(cmd)) < 0) return;
    if (read(ack_fd, b, sizeof b) < 0) return;
}

// ---- in-process core-cycle counter (user-space only; works at paranoid=2) ----
static int cyc_open(void) {
    struct perf_event_attr a;
    memset(&a, 0, sizeof a);
    a.type = PERF_TYPE_HARDWARE;
    a.size = sizeof a;
    a.config = PERF_COUNT_HW_CPU_CYCLES;
    a.exclude_kernel = 1;
    a.exclude_hv = 1;
    return (int)syscall(SYS_perf_event_open, &a, 0, -1, -1, 0);
}
static inline uint64_t cyc_read(int fd) {
    uint64_t v = 0;
    if (fd >= 0 && read(fd, &v, sizeof v) != sizeof v) v = 0;
    return v;
}
#endif
