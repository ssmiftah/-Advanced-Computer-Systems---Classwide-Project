/* main.c - timing + correctness harness.  One invocation measures one kernel/type/variant for a
 * list of sizes, emitting one CSV row per timed sample on stdout (raw samples, no averaging;
 * scripts/process.py computes median/IQR).  The kernels come from kernels_<build>.o, linked into
 * bin/simd_<build>; the build name is taken from argv[0].  See README.md for the methodology. */
#define _GNU_SOURCE
#include <ctype.h>
#include <libgen.h>
#include <math.h>
#include <sched.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include "kernels.h"
#include "perfcyc.h"

enum { K_SAXPY = 0, K_DOT = 1, K_MUL = 2, K_STENCIL = 3 };
enum { V_UNIT = 0, V_STRIDE = 1, V_GATHER = 2 };
enum { G_NONE = 0, G_PERM = 1, G_BLOCK = 2 };

typedef struct {
    const char *exp, *kname, *tname, *vname, *gname;
    int kid, var, gather, samples, check;
    size_t n, stride, off[3];
    double min_ms;
    uint64_t seed;
} cfg_t;

static char g_build[64] = "unknown";
static volatile double g_sink; /* consumes results so nothing is dead-code-eliminated */

#define CATX2(a, b) CAT2_(a, b)
#define CAT2_(a, b) a##_##b
#define CATX3(a, b, c) CAT3_(a, b, c)
#define CAT3_(a, b, c) a##b##_##c

static void die(const char *m)
{
    fprintf(stderr, "error: %s\n", m);
    exit(1);
}

static double now_ns(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC_RAW, &ts);
    return (double)ts.tv_sec * 1e9 + (double)ts.tv_nsec;
}

static uint64_t splitmix(uint64_t *s)
{
    uint64_t z = (*s += 0x9E3779B97F4A7C15ull);
    z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ull;
    z = (z ^ (z >> 27)) * 0x94D049BB133111EBull;
    return z ^ (z >> 31);
}

/* aligned_alloc(64) + pad + byte offset; *base receives the pointer to free(). */
static void *xalloc(size_t bytes, size_t off, size_t pad, void **base)
{
    size_t tot = ((bytes + off + pad + 64 + 63) / 64) * 64;
    void *p = aligned_alloc(64, tot);
    if (!p) die("allocation failed");
    if (base) *base = p;
    return (char *)p + pad + off;
}

/* Index pattern for the gather kernels.  perm: uniformly random permutation of [0,n) (every
 * element read once, no spatial locality).  block: random permutation of whole 16-element blocks,
 * contiguous inside a block (one 64B line for f32), i.e. "gather with partial locality". */
static void build_idx(uint32_t *idx, size_t n, int kind, uint64_t seed)
{
    uint64_t s = seed;
    for (size_t i = 0; i < n; i++) idx[i] = (uint32_t)i;
    if (kind == G_PERM) {
        for (size_t i = n; i > 1; i--) {
            size_t j = splitmix(&s) % i;
            uint32_t t = idx[i - 1]; idx[i - 1] = idx[j]; idx[j] = t;
        }
    } else if (kind == G_BLOCK) {
        size_t nb = n / 16;
        uint32_t *pm = malloc(nb * sizeof *pm);
        if (!pm) die("alloc");
        for (size_t i = 0; i < nb; i++) pm[i] = (uint32_t)i;
        for (size_t i = nb; i > 1; i--) {
            size_t j = splitmix(&s) % i;
            uint32_t t = pm[i - 1]; pm[i - 1] = pm[j]; pm[j] = t;
        }
        for (size_t i = 0; i < nb * 16; i++) idx[i] = pm[i / 16] * 16 + (uint32_t)(i % 16);
        free(pm);
    }
}

/* Nominal per-call cost.  FLOPs: saxpy 2n, dot 2n, mul n, stencil 5(n-2) (3 mul + 2 add; integer
 * kernels count integer ops).  Bytes = algorithmic traffic (loads+stores of useful data, one touch
 * per element; stencil neighbours are reused from cache/registers).  Hardware traffic differs
 * (write-allocate on mul/stencil, whole lines for strided loads) - see README. */
static void kernel_cost(const cfg_t *c, size_t sz, double *flops, double *bytes)
{
    double n = (double)c->n, s = (double)sz;
    switch (c->kid) {
    case K_SAXPY: *flops = 2 * n; *bytes = 3 * n * s; break;
    case K_DOT: *flops = 2 * n; *bytes = 2 * n * s; break;
    case K_MUL: *flops = n; *bytes = 3 * n * s; break;
    default: *flops = 5 * (n - 2); *bytes = 2 * n * s; break;
    }
    if (c->var == V_GATHER) *bytes += 4 * n; /* index array */
}

static const char *HEADER =
    "exp,build,kernel,type,variant,n,n_mod_vw,stride,gather,offx,offy,offz,mis_x,mis_y,ws_bytes,"
    "flops,bytes_nominal,reps,sample,ns_total,cycles,cpu,ns_per_call,gflops,gibs,cyc_per_elem,ghz,seed";

static void emit_row(const cfg_t *c, size_t sz, size_t ws, double flops, double bytes, size_t K,
                     int sample, double ns, int64_t cyc, uintptr_t misx, uintptr_t misy)
{
    double per = ns / (double)K;
    double nan = NAN;
    double ghz = cyc > 0 ? (double)cyc / ns : nan;
    double cpe = cyc > 0 ? (double)cyc / ((double)K * (double)c->n) : nan;
    printf("%s,%s,%s,%s,%s,%zu,%zu,%zu,%s,%zu,%zu,%zu,%lu,%lu,%zu,%.0f,%.0f,%zu,%d,%.1f,%ld,%d,"
           "%.4f,%.5f,%.5f,%.5f,%.5f,%lu\n",
           c->exp, g_build, c->kname, c->tname, c->vname, c->n, c->n % (64 / sz), c->stride,
           c->gname, c->off[0], c->off[1], c->off[2], (unsigned long)misx, (unsigned long)misy, ws,
           flops, bytes, K, sample, ns, (long)cyc, sched_getcpu(), per, flops / per,
           bytes / per * 1e9 / (1024.0 * 1024.0 * 1024.0), cpe, ghz, (unsigned long)c->seed);
}

#define TYP float
#define SFX f32
#define IS_FP 1
#define EPS 1.1920929e-7
#include "harness_t.inc"
#undef TYP
#undef SFX
#undef IS_FP
#undef EPS
#define TYP double
#define SFX f64
#define IS_FP 1
#define EPS 2.220446049250313e-16
#include "harness_t.inc"
#undef TYP
#undef SFX
#undef IS_FP
#undef EPS
#define TYP uint32_t
#define SFX i32
#define IS_FP 0
#define EPS 0
#include "harness_t.inc"

static size_t *parse_list(const char *s, size_t *cnt)
{
    size_t cap = 8, k = 0;
    size_t *v = malloc(cap * sizeof *v);
    while (*s) {
        char *e;
        v[k++] = strtoull(s, &e, 10);
        if (k == cap) v = realloc(v, (cap *= 2) * sizeof *v);
        if (e == s) die("bad list");
        s = *e == ',' ? e + 1 : e;
    }
    *cnt = k;
    return v;
}

static void usage(void)
{
    fputs("usage: simd_<build> --kernel saxpy|dot|mul|stencil --type f32|f64|i32\n"
          "   (--n N1,N2,.. | --ws-kib K1,K2,..) [--variant unit|stride|gather] [--stride S]\n"
          "   [--gather perm|block] [--offset B | --offx B --offy B --offz B] [--samples 15]\n"
          "   [--min-ms 8] [--no-check] [--exp NAME] [--no-header] [--header-only]\n"
          "   ws-kib = nominal footprint of all arrays (n rounded down to a multiple of 64)\n", stderr);
    exit(1);
}

int main(int argc, char **argv)
{
    char *self = strdup(argv[0]);
    const char *bn = basename(self);
    if (!strncmp(bn, "simd_", 5)) snprintf(g_build, sizeof g_build, "%s", bn + 5);

    cfg_t c = {.exp = "adhoc", .kname = "saxpy", .tname = "f32", .vname = "unit", .gname = "none",
               .samples = 15, .check = 1, .stride = 1, .min_ms = 8.0, .seed = 12345};
    size_t *ns = NULL, nn = 0, *ws = NULL, nw = 0;
    int header = 1, header_only = 0;
    for (int i = 1; i < argc; i++) {
        const char *a = argv[i];
#define OPT(name) (!strcmp(a, name) && i + 1 < argc)
        if (OPT("--kernel")) c.kname = argv[++i];
        else if (OPT("--type")) c.tname = argv[++i];
        else if (OPT("--variant")) c.vname = argv[++i];
        else if (OPT("--gather")) c.gname = argv[++i];
        else if (OPT("--exp")) c.exp = argv[++i];
        else if (OPT("--n")) ns = parse_list(argv[++i], &nn);
        else if (OPT("--ws-kib")) ws = parse_list(argv[++i], &nw);
        else if (OPT("--stride")) c.stride = strtoull(argv[++i], NULL, 10);
        else if (OPT("--offset")) c.off[0] = c.off[1] = c.off[2] = strtoull(argv[++i], NULL, 10);
        else if (OPT("--offx")) c.off[0] = strtoull(argv[++i], NULL, 10);
        else if (OPT("--offy")) c.off[1] = strtoull(argv[++i], NULL, 10);
        else if (OPT("--offz")) c.off[2] = strtoull(argv[++i], NULL, 10);
        else if (OPT("--samples")) c.samples = atoi(argv[++i]);
        else if (OPT("--min-ms")) c.min_ms = atof(argv[++i]);
        else if (OPT("--seed")) c.seed = strtoull(argv[++i], NULL, 10);
        else if (!strcmp(a, "--no-check")) c.check = 0;
        else if (!strcmp(a, "--no-header")) header = 0;
        else if (!strcmp(a, "--header-only")) header_only = 1;
        else usage();
    }
    if (header || header_only) puts(HEADER);
    if (header_only) return 0;
    if (!ns && !ws) usage();

    c.kid = !strcmp(c.kname, "saxpy") ? K_SAXPY : !strcmp(c.kname, "dot") ? K_DOT :
            !strcmp(c.kname, "mul") ? K_MUL : !strcmp(c.kname, "stencil") ? K_STENCIL : -1;
    c.var = !strcmp(c.vname, "unit") ? V_UNIT : !strcmp(c.vname, "stride") ? V_STRIDE :
            !strcmp(c.vname, "gather") ? V_GATHER : -1;
    c.gather = !strcmp(c.gname, "perm") ? G_PERM : !strcmp(c.gname, "block") ? G_BLOCK : G_NONE;
    if (c.kid < 0 || c.var < 0) usage();
    if (c.var == V_GATHER && c.gather == G_NONE) die("--variant gather needs --gather perm|block");
    if (c.var != V_GATHER) c.gname = "none";
    if (c.var != V_UNIT && c.kid >= K_MUL) die("stride/gather variants exist for saxpy and dot only");
    if (c.var != V_STRIDE && c.stride != 1 && c.var == V_UNIT) c.stride = 1;
    if (c.var != V_STRIDE) c.stride = 1;
    if (c.var == V_STRIDE && c.stride < 1) die("stride must be >=1");

    int ti = !strcmp(c.tname, "f32") ? 0 : !strcmp(c.tname, "f64") ? 1 : !strcmp(c.tname, "i32") ? 2 : -1;
    if (ti < 0) usage();
    size_t sz = ti == 1 ? 8 : 4, narr = c.kid == K_MUL ? 3 : 2;

    cyc_open();
    if (cyc_fd < 0) fputs("warning: perf cycles counter unavailable; cycle columns will be -1/nan\n", stderr);

    size_t cnt = ns ? nn : nw;
    for (size_t k = 0; k < cnt; k++) {
        c.n = ns ? ns[k] : (ws[k] * 1024 / (narr * sz)) / 64 * 64;
        if (c.n < 4) die("n too small");
        switch (ti) {
        case 0: bench_f32(&c); break;
        case 1: bench_f64(&c); break;
        default: bench_i32(&c); break;
        }
        fflush(stdout);
    }
    if (g_sink == 12345.678) fputs("", stderr); /* keep g_sink observable */
    return 0;
}
