#define _GNU_SOURCE
// Simple array kernels for the cache-miss-impact experiment.
//   mul   : z[i] = x[i] * y[i]           (2 reads + 1 write, 24 B/elem)
//   saxpy : y[i] = a * x[i] + y[i]       (2 reads + 1 write, 24 B/elem, 2 arrays)
// Footprint = total bytes over all arrays (split equally). The work per
// repetition is fixed (--work elements) so runtime is comparable across
// footprints; the kernel is just repeated over the arrays.
//
// Access shape:
//   --pattern seq  : walk blocks in order; --stride E touches only every E-th
//                    BLOCK of --block elements (E=1: dense, unit stride).
//   --pattern rand : the same set of blocks visited in a shuffled order
//                    (precomputed uint32 permutation: costs 4 B per block of
//                    index traffic, ~1% of block traffic for 8-element blocks).
//   --block B      : contiguous elements per block (default 8 doubles = 64 B)
//
// Usage: kernel_miss --footprint BYTES [--kernel mul|saxpy] [--pattern seq|rand]
//        [--stride E] [--block B] [--pages thp|4k] [--work N] [--reps R]
//        [--cpu N] [--header] [--ctl F --ack F]
// Run under `perf stat --control` (scripts/run_kernel.sh) so counters cover
// only the timed repetitions.
#include <getopt.h>
#include "common.h"

static void __attribute__((noinline))
k_mul(double *restrict z, const double *restrict x, const double *restrict y,
      const uint32_t *ord, size_t nblk, size_t B, size_t stride_blk) {
    for (size_t b = 0; b < nblk; b += stride_blk) {
        size_t base = (ord ? (size_t)ord[b] : b) * B;
        for (size_t j = 0; j < B; j++) z[base + j] = x[base + j] * y[base + j];
    }
}
static void __attribute__((noinline))
k_saxpy(double *restrict y, const double *restrict x, double a,
        const uint32_t *ord, size_t nblk, size_t B, size_t stride_blk) {
    for (size_t b = 0; b < nblk; b += stride_blk) {
        size_t base = (ord ? (size_t)ord[b] : b) * B;
        for (size_t j = 0; j < B; j++) y[base + j] = a * x[base + j] + y[base + j];
    }
}

int main(int argc, char **argv) {
    size_t footprint = 3u << 20, B = 8, stride = 1;
    long work = 1L << 28, reps = 5;
    const char *kernel = "mul", *pattern = "seq", *pages = "thp", *ctl = NULL, *ack = NULL;
    int cpu = -1, header = 0;
    static struct option opts[] = {
        {"footprint", 1, 0, 'f'}, {"kernel", 1, 0, 'k'}, {"pattern", 1, 0, 'p'},
        {"stride", 1, 0, 's'},    {"block", 1, 0, 'b'},  {"pages", 1, 0, 'g'},
        {"work", 1, 0, 'w'},      {"reps", 1, 0, 'r'},   {"cpu", 1, 0, 'c'},
        {"header", 0, 0, 'H'},    {"ctl", 1, 0, 'T'},    {"ack", 1, 0, 'A'}, {0, 0, 0, 0}};
    int c;
    while ((c = getopt_long(argc, argv, "", opts, NULL)) != -1) {
        switch (c) {
        case 'f': footprint = strtoull(optarg, NULL, 0); break;
        case 'k': kernel = optarg; break;
        case 'p': pattern = optarg; break;
        case 's': stride = strtoull(optarg, NULL, 0); break;
        case 'b': B = strtoull(optarg, NULL, 0); break;
        case 'g': pages = optarg; break;
        case 'w': work = strtol(optarg, NULL, 0); break;
        case 'r': reps = strtol(optarg, NULL, 0); break;
        case 'c': cpu = atoi(optarg); break;
        case 'H': header = 1; break;
        case 'T': ctl = optarg; break;
        case 'A': ack = optarg; break;
        default: return 1;
        }
    }
    int saxpy = strcmp(kernel, "saxpy") == 0, rnd = strcmp(pattern, "rand") == 0;
    int narr = saxpy ? 2 : 3;
    pin_cpu(cpu);
    size_t n = footprint / narr / sizeof(double);
    n = n / B * B;
    size_t nblk = n / B;
    if (nblk < 2 || stride < 1) { fprintf(stderr, "footprint too small\n"); return 1; }
    size_t arr_bytes = (n * sizeof(double) + 4095) & ~(size_t)4095, maplen;
    char *mem = alloc_pages(arr_bytes * narr, strcmp(pages, "4k") != 0, &maplen);
    memset(mem, 0, maplen);
    double *x = (double *)mem, *y = (double *)(mem + arr_bytes),
           *z = saxpy ? y : (double *)(mem + 2 * arr_bytes);
    for (size_t i = 0; i < n; i++) { x[i] = 1.0 + (i & 7); y[i] = 0.5 + (i & 3); }
    double thp = thp_fraction(&mem, &maplen, 1);

    uint32_t *ord = NULL;
    if (rnd) {  // Fisher-Yates shuffle of block indices
        ord = malloc(nblk * sizeof *ord);
        for (size_t i = 0; i < nblk; i++) ord[i] = (uint32_t)i;
        uint64_t st = 99;
        for (size_t i = nblk - 1; i > 0; i--) {
            size_t j = xs64(&st) % (i + 1);
            uint32_t t = ord[i]; ord[i] = ord[j]; ord[j] = t;
        }
    }
    size_t elems_per_pass = ((nblk + stride - 1) / stride) * B;
    long passes = work / (long)elems_per_pass;
    if (passes < 1) passes = 1;
    double a = 1.0000001;  // keeps saxpy values bounded over many passes

    if (header)
        puts("kernel,pattern,stride_blocks,block_elems,pages,footprint,thp_frac,rep,passes,seconds,"
             "ns_per_elem,useful_GBps,elems");
    ctl_open(ctl, ack);
    for (int w = 0; w < 1; w++) {  // warm-up pass (not timed, counters disabled)
        if (saxpy) k_saxpy(y, x, a, ord, nblk, B, stride);
        else k_mul(z, x, y, ord, nblk, B, stride);
    }
    ctl_cmd("enable");
    for (long r = 0; r < reps; r++) {
        double t0 = now_ns();
        for (long p = 0; p < passes; p++) {
            if (saxpy) k_saxpy(y, x, a, ord, nblk, B, stride);
            else k_mul(z, x, y, ord, nblk, B, stride);
        }
        double t1 = now_ns();
        double elems = (double)passes * elems_per_pass;
        printf("%s,%s,%zu,%zu,%s,%zu,%.3f,%ld,%ld,%.5f,%.5f,%.4f,%.0f\n", kernel, pattern, stride, B,
               pages, footprint, thp, r, passes, (t1 - t0) / 1e9, (t1 - t0) / elems,
               elems * 24.0 / (t1 - t0), elems);
    }
    ctl_cmd("disable");
    double chk = 0;
    for (size_t i = 0; i < n; i += 97) chk += z[i];
    if (chk == 1.2345) fprintf(stderr, "chk\n");
    return 0;
}
