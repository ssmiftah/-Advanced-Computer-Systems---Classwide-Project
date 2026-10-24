/* peakflops.c - empirical FMA throughput ceiling for the roofline.
 * Independent FMA chains held in registers (no memory traffic).  16 accumulators >= pipes x
 * latency (Zen 5: 2 FMA pipes x ~4-cycle latency => 8 needed), so throughput not latency bound.
 * Rows: kind (fp32/fp64 at 512/256/128-bit), measured GFLOP/s, measured core cycles and the
 * resulting FLOP/cycle.  Theoretical Zen 5 (desktop, full 512-bit datapath): 2 FMA pipes x 16
 * fp32 lanes x 2 FLOP = 64 FLOP/cycle/core fp32 (32 fp64); see README for the sourcing caveat. */
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

/* Each function runs `iters` loop iterations x 16 FMAs; returns a value to be consumed. */
#define DEFK(NAME, VT, FMA, SET1, ELT, NL)                                                   \
    static double NAME(size_t iters)                                                         \
    {                                                                                        \
        VT acc[16], b = SET1((ELT)1.0000001), c = SET1((ELT)1e-9);                           \
        for (int i = 0; i < 16; i++) acc[i] = SET1((ELT)(0.5 + 0.01 * i));                   \
        for (size_t it = 0; it < iters; it++)                                                \
            _Pragma("GCC unroll 16")                                                         \
            for (int i = 0; i < 16; i++) acc[i] = FMA(acc[i], b, c);                         \
        ELT tmp[NL], tot = 0;                                                                \
        for (int i = 0; i < 16; i++) {                                                       \
            memcpy(tmp, &acc[i], sizeof tmp);                                                \
            for (int j = 0; j < NL; j++) tot += tmp[j];                                      \
        }                                                                                    \
        return (double)tot;                                                                  \
    }
DEFK(k_f32_512, __m512, _mm512_fmadd_ps, _mm512_set1_ps, float, 16)
DEFK(k_f32_256, __m256, _mm256_fmadd_ps, _mm256_set1_ps, float, 8)
DEFK(k_f32_128, __m128, _mm_fmadd_ps, _mm_set1_ps, float, 4)
DEFK(k_f64_512, __m512d, _mm512_fmadd_pd, _mm512_set1_pd, double, 8)

int main(int argc, char **argv)
{
    int samples = 9;
    double min_ms = 50;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--samples") && i + 1 < argc) samples = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--min-ms") && i + 1 < argc) min_ms = atof(argv[++i]);
    }
    struct { const char *name; double (*f)(size_t); double flop_per_iter; } K[] = {
        {"fp32_zmm", k_f32_512, 16 * 16 * 2.0}, {"fp32_ymm", k_f32_256, 16 * 8 * 2.0},
        {"fp32_xmm", k_f32_128, 16 * 4 * 2.0},  {"fp64_zmm", k_f64_512, 16 * 8 * 2.0}};
    cyc_open();
    puts("exp,kind,sample,iters,ns_total,cycles,cpu,gflops,flop_per_cycle,ghz");
    volatile double sink = 0;
    for (size_t k = 0; k < sizeof K / sizeof *K; k++) {
        size_t iters = 1 << 16;
        for (;;) {
            double t0 = now_ns();
            sink += K[k].f(iters);
            double dt = now_ns() - t0;
            if (dt >= min_ms * 1e6) break;
            iters *= 2;
        }
        for (int s = 0; s < samples; s++) {
            int64_t c0 = cyc_read();
            double t0 = now_ns();
            sink += K[k].f(iters);
            double dt = now_ns() - t0;
            int64_t c1 = cyc_read();
            double fl = K[k].flop_per_iter * (double)iters;
            int ok = c0 >= 0 && c1 >= 0;
            printf("peakflops,%s,%d,%zu,%.1f,%ld,%d,%.4f,%.4f,%.4f\n", K[k].name, s, iters, dt,
                   ok ? (long)(c1 - c0) : -1L, sched_getcpu(), fl / dt,
                   ok ? fl / (double)(c1 - c0) : -1.0, ok ? (double)(c1 - c0) / dt : -1.0);
        }
    }
    (void)sink;
    return 0;
}
