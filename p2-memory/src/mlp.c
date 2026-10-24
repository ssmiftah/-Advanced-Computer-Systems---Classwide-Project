#define _GNU_SOURCE
// Memory-level-parallelism / loaded-latency benchmark.
//
// (a) MLP mode (default): each of --threads chase threads walks K independent
//     random pointer chains (--chains K) interleaved in one loop. Every hop is a
//     dependent load within its chain, but the K chains overlap, so ~K cache-line
//     requests are outstanding per thread. Measured: latency per hop, and
//     throughput = hops * 64 B / time. Little's law: outstanding = throughput *
//     latency (a consistency check, since K*threads is the configured value).
// (b) MLC-style loaded latency (--bg N): the chase threads (usually 1 thread,
//     K=1 = pure latency probe) run while N background threads stream through
//     their own buffers with an injected delay (--bgdelay iterations of a ~1
//     cycle add per 64 B line) to dial the load from idle (huge delay) to
//     maximum (0). --bgrw R:W sets the background read:write line mix
//     (normal stores, i.e. write-allocate).
//
// Usage: mlp --size BYTES_PER_CHASE_THREAD [--threads T] [--cpus list]
//        [--chains K] [--bg N --bgcpus list --bgdelay D --bgrw R:W --bgsize B]
//        [--pages thp|4k] [--secs S] [--reps R] [--header] [--ctl F --ack F]
//
// Chains live in disjoint sub-buffers of size/K bytes, one node per 64 B line,
// each a single Sattolo cycle (so no line is reused within a lap and hardware
// prefetchers cannot guess the next address).
#include <getopt.h>
#include <immintrin.h>
#include "common.h"

#define KLIST(X) X(1) X(2) X(3) X(4) X(5) X(6) X(8) X(10) X(12) X(16) X(20) X(24) X(32) X(48) X(64)
#define DEF(K_)                                                                         \
    static void chase_##K_(void **p, long steps) {                                      \
        void *q[K_];                                                                    \
        memcpy(q, p, sizeof q);                                                         \
        for (long s = 0; s < steps; s++) {                                              \
            _Pragma("GCC unroll 64") for (int j = 0; j < K_; j++) q[j] = *(void **)q[j]; \
        }                                                                               \
        memcpy(p, q, sizeof q);                                                         \
    }
KLIST(DEF)
typedef void (*chase_fn)(void **, long);
static chase_fn pick_chase(int k) {
#define CASE(K_) if (k == K_) return chase_##K_;
    KLIST(CASE)
    fprintf(stderr, "unsupported --chains %d\n", k);
    exit(1);
}

static struct {
    int nthreads, ncpu, cpus[128], nbg, nbgcpu, bgcpus[128], K, thp, R, W;
    size_t size, bgsize;
    long bgdelay, reps;
    double secs;
} cfg = {.nthreads = 1, .K = 1, .thp = 1, .R = 1, .size = 256u << 20, .bgsize = 128u << 20,
         .reps = 5, .secs = 0.5};

typedef struct {
    int tid, bg;
    char *buf;
    size_t maplen;
    double elapsed_ns;
    uint64_t hops, bytes_r, bytes_w;  // hops = steps*K
    uint64_t sink;
} targ_t;

static pthread_barrier_t bar;
static volatile double g_t0, g_deadline;
static double g_thp = -1;

static void build_chains(char *buf, int K, size_t total, uint64_t seed, void **start) {
    size_t per = total / K / 64;  // nodes per chain
    size_t *ord = malloc(per * sizeof *ord);
    uint64_t st = seed | 1;
    for (int k = 0; k < K; k++) {
        char *base = buf + (size_t)k * per * 64;
        for (size_t i = 0; i < per; i++) ord[i] = i;
        for (size_t i = per - 1; i > 0; i--) {  // Sattolo: one cycle
            size_t j = xs64(&st) % i;
            size_t t = ord[i]; ord[i] = ord[j]; ord[j] = t;
        }
        for (size_t i = 0; i < per; i++)
            *(void **)(base + ord[i] * 64) = base + ord[(i + 1) % per] * 64;
        start[k] = base + ord[0] * 64;
    }
    free(ord);
}

static void *chase_worker(void *arg) {
    targ_t *a = arg;
    if (cfg.ncpu) pin_cpu(cfg.cpus[a->tid % cfg.ncpu]);
    a->buf = alloc_pages(cfg.size, cfg.thp, &a->maplen);
    memset(a->buf, 0, a->maplen);
    void *p[64];
    build_chains(a->buf, cfg.K, cfg.size, 1234567ULL * (a->tid + 1), p);
    chase_fn fn = pick_chase(cfg.K);
    long chunk = 4096 / cfg.K + 1;
    fn(p, chunk);  // warm up
    pthread_barrier_wait(&bar);  // INIT
    for (long rep = 0; rep < cfg.reps; rep++) {
        a->hops = 0;
        pthread_barrier_wait(&bar);  // A
        if (a->tid == 0) { double t0 = now_ns(); g_t0 = t0; g_deadline = t0 + cfg.secs * 1e9; }
        pthread_barrier_wait(&bar);  // B
        double t0 = g_t0, dl = g_deadline, t;
        do {
            fn(p, chunk);
            a->hops += (uint64_t)chunk * cfg.K;
            t = now_ns();
        } while (t < dl);
        a->elapsed_ns = t - t0;
        pthread_barrier_wait(&bar);  // C
        pthread_barrier_wait(&bar);  // D
    }
    a->sink = (uint64_t)p[0];
    return NULL;
}

static void *bg_worker(void *arg) {
    targ_t *a = arg;
    if (cfg.nbgcpu) pin_cpu(cfg.bgcpus[a->tid % cfg.nbgcpu]);
    a->buf = alloc_pages(cfg.bgsize, cfg.thp, &a->maplen);
    memset(a->buf, 0x5a, a->maplen);
    size_t nl = cfg.bgsize / 64;
    const int P = cfg.R + cfg.W;
    const __m512i v = _mm512_set1_epi64(7);
    __m512i acc = _mm512_setzero_si512();
    uint64_t x = 0;
    pthread_barrier_wait(&bar);  // INIT
    for (long rep = 0; rep < cfg.reps; rep++) {
        a->bytes_r = a->bytes_w = 0;
        pthread_barrier_wait(&bar);  // A
        pthread_barrier_wait(&bar);  // B
        double dl = g_deadline, t0 = g_t0, t;
        size_t i = 0;
        do {
            // 4096 lines (256 KiB) per clock check
            uint64_t nr = 0, nw = 0;
            for (int b = 0; b < 4096; b++) {
                char *p = a->buf + i * 64;
                if ((int)((i) % P) < cfg.R) { acc = _mm512_add_epi64(acc, _mm512_load_si512(p)); nr++; }
                else { _mm512_store_si512(p, v); nw++; }
                if (++i == nl) i = 0;
                for (long d = 0; d < cfg.bgdelay; d++) __asm__ volatile("add $1, %0" : "+r"(x));
            }
            a->bytes_r += nr * 64; a->bytes_w += nw * 64;
            t = now_ns();
        } while (t < dl);
        a->elapsed_ns = t - t0;
        pthread_barrier_wait(&bar);  // C
        pthread_barrier_wait(&bar);  // D
    }
    a->sink = x ^ (uint64_t)_mm512_reduce_add_epi64(acc);
    return NULL;
}

int main(int argc, char **argv) {
    const char *cpus = "4,5,6,7", *bgcpus = "5,6,7", *ctl = NULL, *ack = NULL, *pages = "thp", *bgrw = "1:0";
    int header = 0;
    static struct option opts[] = {
        {"size", 1, 0, 'z'}, {"threads", 1, 0, 't'}, {"cpus", 1, 0, 'c'}, {"chains", 1, 0, 'k'},
        {"bg", 1, 0, 'b'},   {"bgcpus", 1, 0, 'C'},  {"bgdelay", 1, 0, 'D'}, {"bgrw", 1, 0, 'm'},
        {"bgsize", 1, 0, 'Z'}, {"pages", 1, 0, 'g'}, {"secs", 1, 0, 'd'}, {"reps", 1, 0, 'r'},
        {"header", 0, 0, 'H'}, {"ctl", 1, 0, 'T'},   {"ack", 1, 0, 'A'},  {0, 0, 0, 0}};
    int c;
    while ((c = getopt_long(argc, argv, "", opts, NULL)) != -1) {
        switch (c) {
        case 'z': cfg.size = strtoull(optarg, NULL, 0); break;
        case 't': cfg.nthreads = atoi(optarg); break;
        case 'c': cpus = optarg; break;
        case 'k': cfg.K = atoi(optarg); break;
        case 'b': cfg.nbg = atoi(optarg); break;
        case 'C': bgcpus = optarg; break;
        case 'D': cfg.bgdelay = atol(optarg); break;
        case 'm': bgrw = optarg; break;
        case 'Z': cfg.bgsize = strtoull(optarg, NULL, 0); break;
        case 'g': pages = optarg; break;
        case 'd': cfg.secs = atof(optarg); break;
        case 'r': cfg.reps = atol(optarg); break;
        case 'H': header = 1; break;
        case 'T': ctl = optarg; break;
        case 'A': ack = optarg; break;
        default: return 1;
        }
    }
    if (sscanf(bgrw, "%d:%d", &cfg.R, &cfg.W) != 2 || cfg.R + cfg.W == 0) return 1;
    cfg.thp = strcmp(pages, "4k") != 0;
    cfg.ncpu = parse_cpus(cpus, cfg.cpus, 128);
    cfg.nbgcpu = parse_cpus(bgcpus, cfg.bgcpus, 128);
    pick_chase(cfg.K);
    if (cfg.size / cfg.K < 64 * 16) { fprintf(stderr, "size too small for K chains\n"); return 1; }

    int total = cfg.nthreads + cfg.nbg;
    pthread_barrier_init(&bar, NULL, total + 1);
    pthread_t th[256];
    static targ_t ta[256];
    for (int i = 0; i < total; i++) {
        ta[i].tid = i < cfg.nthreads ? i : i - cfg.nthreads;
        ta[i].bg = i >= cfg.nthreads;
        pthread_create(&th[i], NULL, ta[i].bg ? bg_worker : chase_worker, &ta[i]);
    }
    if (header)
        puts("chase_threads,chains,outstanding_cfg,bg_threads,bg_delay,bg_rw,pages,size_per_thread,"
             "thp_frac,rep,seconds,lat_ns_mean,lat_ns_min,lat_ns_max,chase_GBps,bg_GBps,"
             "bg_est_mem_GBps,total_GBps,outstanding_littles");
    ctl_open(ctl, ack);
    pthread_barrier_wait(&bar);  // INIT
    {
        char *bufs[256]; size_t lens[256];
        for (int i = 0; i < total; i++) { bufs[i] = ta[i].buf; lens[i] = ta[i].maplen; }
        g_thp = thp_fraction(bufs, lens, total);
    }
    ctl_cmd("enable");
    for (long rep = 0; rep < cfg.reps; rep++) {
        pthread_barrier_wait(&bar);  // A
        pthread_barrier_wait(&bar);  // B
        pthread_barrier_wait(&bar);  // C
        double lsum = 0, lmin = 1e30, lmax = 0, hops = 0, tmax = 0, bgr = 0, bgw = 0, bgt = 0;
        for (int i = 0; i < cfg.nthreads; i++) {
            // per-thread latency per hop: each chain advances one hop per "step"
            double lat = ta[i].elapsed_ns / ((double)ta[i].hops / cfg.K);
            lsum += lat;
            if (lat < lmin) lmin = lat;
            if (lat > lmax) lmax = lat;
            hops += ta[i].hops;
            if (ta[i].elapsed_ns > tmax) tmax = ta[i].elapsed_ns;
        }
        for (int i = cfg.nthreads; i < total; i++) {
            bgr += ta[i].bytes_r; bgw += ta[i].bytes_w;
            if (ta[i].elapsed_ns > bgt) bgt = ta[i].elapsed_ns;
        }
        double chase_gbps = hops * 64.0 / tmax;
        double bg_gbps = bgt > 0 ? (bgr + bgw) / bgt : 0;
        double bg_mem = bgt > 0 ? (bgr + 2 * bgw) / bgt : 0;
        double lat = lsum / cfg.nthreads;
        double tot = chase_gbps + bg_gbps;
        // Little: outstanding lines = (lines/s) * latency(s); GB/s * ns / 64 B.
        double little = (chase_gbps / 64.0) * lat;
        printf("%d,%d,%d,%d,%ld,%d:%d,%s,%zu,%.3f,%ld,%.4f,%.3f,%.3f,%.3f,%.4f,%.4f,%.4f,%.4f,%.3f\n",
               cfg.nthreads, cfg.K, cfg.nthreads * cfg.K, cfg.nbg, cfg.bgdelay, cfg.R, cfg.W, pages,
               cfg.size, g_thp, rep, tmax / 1e9, lat, lmin, lmax, chase_gbps, bg_gbps, bg_mem, tot,
               little);
        fflush(stdout);
        pthread_barrier_wait(&bar);  // D
    }
    ctl_cmd("disable");
    uint64_t s = 0;
    for (int i = 0; i < total; i++) { pthread_join(th[i], NULL); s ^= ta[i].sink; }
    if (s == 0x1234) fprintf(stderr, "sink\n");
    return 0;
}
