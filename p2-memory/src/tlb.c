#define _GNU_SOURCE
// TLB-reach benchmark: pointer chase with ONE node per page.
//
// The chain visits `span/stride` pages (stride = page spacing, default 4 KiB),
// touching a single 64 B line in each. The cache footprint is therefore only
// (#pages x 64 B) while the TLB footprint is #pages entries: with 4 KiB pages
// the L1 dTLB / L2 dTLB (STLB) reach is exceeded after a few MiB / tens of
// MiB of span, with 2 MiB THP pages the same span needs 512x fewer entries.
// The line offset inside each page is varied pseudo-randomly (hash of the page
// number) so the nodes do not all alias into the same few L1/L2 sets.
// Note: for spans >~ 2 GiB the node lines themselves (span/4096 x 64 B) start to
// exceed the 64 MiB of L3, so a 4k-vs-THP difference at equal span is the clean
// TLB signal, not the absolute value.
//
// Usage: tlb --span BYTES [--pages thp|4k] [--order random|seq] [--stride B]
//        [--steps N] [--reps R] [--cpu N] [--header] [--ctl F --ack F]
// CSV: span_bytes,stride,pages_touched,pages,order,thp_frac,rep,ns_per_access,steps
#include <getopt.h>
#include "common.h"

int main(int argc, char **argv) {
    size_t span = 64u << 20, stride = 4096;
    long steps = 0, reps = 5;
    const char *pages = "4k", *order = "random", *ctl = NULL, *ack = NULL;
    int cpu = -1, header = 0;
    static struct option opts[] = {
        {"span", 1, 0, 'z'}, {"pages", 1, 0, 'g'}, {"order", 1, 0, 'o'}, {"stride", 1, 0, 's'},
        {"steps", 1, 0, 'n'}, {"reps", 1, 0, 'r'}, {"cpu", 1, 0, 'c'},   {"header", 0, 0, 'H'},
        {"ctl", 1, 0, 'T'},  {"ack", 1, 0, 'A'},   {0, 0, 0, 0}};
    int c;
    while ((c = getopt_long(argc, argv, "", opts, NULL)) != -1) {
        switch (c) {
        case 'z': span = strtoull(optarg, NULL, 0); break;
        case 'g': pages = optarg; break;
        case 'o': order = optarg; break;
        case 's': stride = strtoull(optarg, NULL, 0); break;
        case 'n': steps = strtol(optarg, NULL, 0); break;
        case 'r': reps = strtol(optarg, NULL, 0); break;
        case 'c': cpu = atoi(optarg); break;
        case 'H': header = 1; break;
        case 'T': ctl = optarg; break;
        case 'A': ack = optarg; break;
        default: return 1;
        }
    }
    if (stride < 128 || stride % 64) { fprintf(stderr, "bad stride\n"); return 1; }
    size_t n = span / stride;
    if (n < 2) { fprintf(stderr, "span too small\n"); return 1; }
    pin_cpu(cpu);
    size_t maplen;
    char *buf = alloc_pages(n * stride, strcmp(pages, "4k") != 0, &maplen);
    memset(buf, 0, maplen);
    double thp = thp_fraction(&buf, &maplen, 1);

    size_t *ord = malloc(n * sizeof *ord);
    for (size_t i = 0; i < n; i++) ord[i] = i;
    if (strcmp(order, "random") == 0) {
        uint64_t st = 4242;
        for (size_t i = n - 1; i > 0; i--) {
            size_t j = xs64(&st) % i;
            size_t t = ord[i]; ord[i] = ord[j]; ord[j] = t;
        }
    }
    #define NODE(pg) ((void **)(buf + (pg) * stride + ((((pg) * 2654435761u) >> 7) & ((stride / 64) - 1 < 63 ? (stride / 64) - 1 : 63)) * 64))
    for (size_t i = 0; i < n; i++) *NODE(ord[i]) = NODE(ord[(i + 1) % n]);
    void **p = NODE(ord[0]);
    free(ord);
    if (steps == 0) steps = n * 2 > 20000000 ? (long)n * 2 : 20000000;
    for (size_t i = 0; i < n; i++) p = (void **)*p;  // warm-up lap

    if (header) puts("span_bytes,stride,pages_touched,pages,order,thp_frac,rep,ns_per_access,steps");
    ctl_open(ctl, ack);
    ctl_cmd("enable");
    for (long r = 0; r < reps; r++) {
        double t0 = now_ns();
        for (long i = 0; i < steps; i += 8) {
            p = (void **)*p; p = (void **)*p; p = (void **)*p; p = (void **)*p;
            p = (void **)*p; p = (void **)*p; p = (void **)*p; p = (void **)*p;
        }
        double t1 = now_ns();
        printf("%zu,%zu,%zu,%s,%s,%.3f,%ld,%.4f,%ld\n", span, stride, n, pages, order, thp, r,
               (t1 - t0) / steps, steps);
    }
    ctl_cmd("disable");
    if (p == NULL) fprintf(stderr, "unreachable\n");
    return 0;
}
