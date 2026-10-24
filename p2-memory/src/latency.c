#define _GNU_SOURCE
// Pointer-chasing latency benchmark.
// Each load's address depends on the previous load, so the CPU cannot overlap
// them: time per step ~= load-to-use latency of whichever level holds the buffer.
//
// Usage: latency --size BYTES [--pattern random|seq] [--stride BYTES]
//                [--pages thp|4k] [--steps N] [--reps R] [--seed S]
// Output: one CSV row per repetition:
//   size_bytes,pattern,stride,pages,rep,ns_per_access[,thp_frac,core_ghz]
// Extensions (added for Project 2, original behaviour unchanged):
//   --header     print a CSV header line (with the two extra columns)
//   --cycles     measure core cycles over the timed loop (perf_event_open,
//                user-space) and report the real core clock in GHz
//   --cpu N      pin to CPU N (default: whatever the caller used, e.g. taskset)
//   --ctl/--ack  perf-stat --control fifos: counters enabled only while timing
#include <getopt.h>
#include "common.h"

// xorshift64* RNG: deterministic for a given seed, so runs are reproducible.
static uint64_t rng_state;
static uint64_t rng(void) {
    rng_state ^= rng_state >> 12;
    rng_state ^= rng_state << 25;
    rng_state ^= rng_state >> 27;
    return rng_state * 2685821657736338717ULL;
}

int main(int argc, char **argv) {
    size_t size = 1 << 20, stride = 64;
    long steps = 0, reps = 11;
    const char *pattern = "random", *pages = "thp";
    uint64_t seed = 42;
    int header = 0, want_cycles = 0, cpu = -1;
    const char *ctl = NULL, *ack = NULL;

    static struct option opts[] = {
        {"size", 1, 0, 'z'},  {"pattern", 1, 0, 'p'}, {"stride", 1, 0, 's'},
        {"pages", 1, 0, 'g'}, {"steps", 1, 0, 'n'},   {"reps", 1, 0, 'r'},
        {"seed", 1, 0, 'e'},  {"header", 0, 0, 'H'},   {"cycles", 0, 0, 'C'},
        {"cpu", 1, 0, 'c'},   {"ctl", 1, 0, 'T'},     {"ack", 1, 0, 'A'},
        {0, 0, 0, 0}};
    int c;
    while ((c = getopt_long(argc, argv, "", opts, NULL)) != -1) {
        switch (c) {
        case 'z': size = strtoull(optarg, NULL, 0); break;
        case 'p': pattern = optarg; break;
        case 's': stride = strtoull(optarg, NULL, 0); break;
        case 'g': pages = optarg; break;
        case 'n': steps = strtol(optarg, NULL, 0); break;
        case 'r': reps = strtol(optarg, NULL, 0); break;
        case 'e': seed = strtoull(optarg, NULL, 0); break;
        case 'H': header = 1; break;
        case 'C': want_cycles = 1; break;
        case 'c': cpu = atoi(optarg); break;
        case 'T': ctl = optarg; break;
        case 'A': ack = optarg; break;
        default: return 1;
        }
    }
    if (stride < sizeof(void *) || stride % sizeof(void *)) {
        fprintf(stderr, "stride must be a multiple of %zu\n", sizeof(void *));
        return 1;
    }
    size_t n = size / stride;  // number of nodes in the chain
    if (n < 2) { fprintf(stderr, "size too small for stride\n"); return 1; }

    pin_cpu(cpu);
    // Allocate with mmap so we control page size via madvise (2 MiB aligned so
    // THP can actually back the whole buffer).
    size_t map_len;
    char *buf = alloc_pages(n * stride, strcmp(pages, "4k") != 0, &map_len);
    memset(buf, 0, map_len);  // fault pages in before timing
    double thp = thp_fraction(&buf, &map_len, 1);

    // Build the visiting order. random: Sattolo's algorithm gives one cycle
    // through all nodes, so the chase touches every node exactly once per lap.
    size_t *order = malloc(n * sizeof *order);
    for (size_t i = 0; i < n; i++) order[i] = i;
    if (strcmp(pattern, "random") == 0) {
        rng_state = seed ? seed : 1;
        for (size_t i = n - 1; i > 0; i--) {
            size_t j = rng() % i;  // j < i (Sattolo, not Fisher-Yates)
            size_t t = order[i]; order[i] = order[j]; order[j] = t;
        }
    }
    for (size_t i = 0; i < n; i++) {
        void **node = (void **)(buf + order[i] * stride);
        *node = buf + order[(i + 1) % n] * stride;
    }
    free(order);

    // Enough steps for ~tens of ms per rep, and at least 4 laps of the chain.
    if (steps == 0) steps = n * 4 > 20000000 ? (long)n * 4 : 20000000;

    void **p = (void **)buf;
    for (size_t i = 0; i < n; i++) p = (void **)*p;  // warm-up lap

    if (header) puts("size_bytes,pattern,stride,pages,rep,ns_per_access,thp_frac,core_ghz");
    ctl_open(ctl, ack);
    int cfd = want_cycles ? cyc_open() : -1;
    if (want_cycles && cfd < 0) perror("perf_event_open(cycles)");
    ctl_cmd("enable");
    for (long r = 0; r < reps; r++) {
        uint64_t c0 = cyc_read(cfd);
        double t0 = now_ns();
        for (long i = 0; i < steps; i += 8) {  // unrolled; still fully serial
            p = (void **)*p; p = (void **)*p; p = (void **)*p; p = (void **)*p;
            p = (void **)*p; p = (void **)*p; p = (void **)*p; p = (void **)*p;
        }
        double t1 = now_ns();
        uint64_t c1 = cyc_read(cfd);
        double ghz = (cfd >= 0 && c1 > c0) ? (double)(c1 - c0) / (t1 - t0) : -1;
        printf("%zu,%s,%zu,%s,%ld,%.4f,%.3f,%.3f\n", size, pattern, stride, pages, r,
               (t1 - t0) / steps, thp, ghz);
    }
    ctl_cmd("disable");
    // Use p so the compiler cannot delete the chase loop.
    if (p == NULL) fprintf(stderr, "unreachable\n");
    munmap(buf, map_len);
    return 0;
}
