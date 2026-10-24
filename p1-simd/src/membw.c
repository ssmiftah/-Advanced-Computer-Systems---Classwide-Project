/* membw.c - single-thread streaming bandwidth vs. buffer size (self-contained roofline input).
 *   read : sum of a buffer using 512-bit loads, 8 independent accumulators
 *   triad: a[i] = b[i] + s*c[i] (2 reads + 1 write, regular stores => write-allocate traffic is
 *          NOT counted in the reported GiB/s; counted bytes = 3*size/3 buffers... see below)
 * Buffer sizes are per-array bytes for triad; for read the buffer itself.  One CSV row per sample.
 * NOTE: this is ONE core.  A single Zen 5 core cannot saturate DRAM; the multi-thread number
 * (Project 2) is the right DRAM ceiling for a multi-core roofline, the single-thread number is
 * the right ceiling for the single-threaded kernels measured here. */
#define _GNU_SOURCE
#include <immintrin.h>
#include <sched.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include "perfcyc.h"

static double now_ns(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC_RAW, &ts);
    return (double)ts.tv_sec * 1e9 + (double)ts.tv_nsec;
}

static float read_pass(const float *p, size_t n)
{
    __m512 a0 = _mm512_setzero_ps(), a1 = a0, a2 = a0, a3 = a0, a4 = a0, a5 = a0, a6 = a0, a7 = a0;
    for (size_t i = 0; i + 128 <= n; i += 128) {
        a0 = _mm512_add_ps(a0, _mm512_load_ps(p + i));
        a1 = _mm512_add_ps(a1, _mm512_load_ps(p + i + 16));
        a2 = _mm512_add_ps(a2, _mm512_load_ps(p + i + 32));
        a3 = _mm512_add_ps(a3, _mm512_load_ps(p + i + 48));
        a4 = _mm512_add_ps(a4, _mm512_load_ps(p + i + 64));
        a5 = _mm512_add_ps(a5, _mm512_load_ps(p + i + 80));
        a6 = _mm512_add_ps(a6, _mm512_load_ps(p + i + 96));
        a7 = _mm512_add_ps(a7, _mm512_load_ps(p + i + 112));
    }
    a0 = _mm512_add_ps(_mm512_add_ps(a0, a1), _mm512_add_ps(a2, a3));
    a4 = _mm512_add_ps(_mm512_add_ps(a4, a5), _mm512_add_ps(a6, a7));
    return _mm512_reduce_add_ps(_mm512_add_ps(a0, a4));
}

static void triad_pass(float *a, const float *b, const float *c, size_t n, float s)
{
    __m512 vs = _mm512_set1_ps(s);
    for (size_t i = 0; i + 16 <= n; i += 16)
        _mm512_store_ps(a + i, _mm512_fmadd_ps(vs, _mm512_load_ps(c + i), _mm512_load_ps(b + i)));
}

int main(int argc, char **argv)
{
    const char *sizes = "32,1024,65536", *mode = "read", *exp = "bandwidth";
    int samples = 15, header = 1;
    double min_ms = 20;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--sizes-kib") && i + 1 < argc) sizes = argv[++i];
        else if (!strcmp(argv[i], "--mode") && i + 1 < argc) mode = argv[++i];
        else if (!strcmp(argv[i], "--samples") && i + 1 < argc) samples = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--min-ms") && i + 1 < argc) min_ms = atof(argv[++i]);
        else if (!strcmp(argv[i], "--no-header")) header = 0;
        else { fputs("usage: membw [--mode read|triad] [--sizes-kib a,b,..] [--samples N] [--min-ms M] [--no-header]\n", stderr); return 1; }
    }
    int triad = !strcmp(mode, "triad");
    cyc_open();
    if (header) puts("exp,mode,size_kib,reps,sample,ns_total,cycles,cpu,bytes_per_pass,gibs,ghz");
    char *list = strdup(sizes);
    for (char *tok = strtok(list, ","); tok; tok = strtok(NULL, ",")) {
        size_t kib = strtoull(tok, NULL, 10), n = kib * 1024 / sizeof(float); /* floats per array */
        n = n / 128 * 128;
        float *a = aligned_alloc(64, n * 4), *b = aligned_alloc(64, n * 4), *c = aligned_alloc(64, n * 4);
        if (!a || !b || !c) { fputs("alloc failed\n", stderr); return 1; }
        for (size_t i = 0; i < n; i++) { a[i] = 0.5f; b[i] = 1.0f + (float)(i & 7) * 0.125f; c[i] = 0.25f; }
        volatile float sink = 0;
        size_t K = 1;
        for (;;) { /* calibrate (doubles as warm-up) */
            double t0 = now_ns();
            for (size_t r = 0; r < K; r++) { if (triad) triad_pass(a, b, c, n, 1.0001f); else sink += read_pass(b, n); }
            double dt = now_ns() - t0;
            if (dt >= min_ms * 1e6) break;
            K = K * (size_t)(min_ms * 1e6 * 1.2 / (dt > 1000 ? dt : 1000) < 2 ? 2 : min_ms * 1e6 * 1.2 / (dt > 1000 ? dt : 1000)) + 1;
        }
        /* triad counts 3 arrays moved (2 reads + 1 write); write-allocate extra read not counted */
        double bytes = (triad ? 3.0 : 1.0) * (double)n * 4.0;
        for (int s = 0; s < samples; s++) {
            int64_t c0 = cyc_read();
            double t0 = now_ns();
            for (size_t r = 0; r < K; r++) { if (triad) triad_pass(a, b, c, n, 1.0001f); else sink += read_pass(b, n); }
            double dt = now_ns() - t0;
            int64_t c1 = cyc_read();
            double total = bytes * (double)K;
            printf("%s,%s,%zu,%zu,%d,%.1f,%ld,%d,%.0f,%.4f,%.4f\n", exp, mode, kib, K, s, dt,
                   (c0 < 0 || c1 < 0) ? -1L : (long)(c1 - c0), sched_getcpu(), bytes,
                   total / dt * 1e9 / (1024.0 * 1024.0 * 1024.0),
                   (c0 < 0 || c1 < 0) ? -1.0 : (double)(c1 - c0) / dt);
        }
        fflush(stdout);
        (void)sink; free(a); free(b); free(c);
    }
    return 0;
}
