#define _GNU_SOURCE
// Multi-threaded bandwidth benchmark: read / write / mixed R:W, sequential or
// random block order, configurable stride and access size, pinned threads.
//
// Usage: bandwidth --size BYTES_PER_THREAD [--threads N] [--cpus 4,5,6,7|none]
//          [--rw R:W] [--nt] [--pattern seq|rand] [--stride B] [--access 64|8]
//          [--pages thp|4k] [--secs S] [--reps R] [--nowarm] [--header]
//          [--ctl FIFO --ack FIFO]
//
// Model: every thread owns a private buffer (first-touched by the thread, so it
// is local to its CCD) of `size` bytes, viewed as size/stride "blocks". One
// *access* touches `access` bytes at the start of a block: 64 = one AVX-512
// 64 B load/store (one full cache line), 8 = one scalar 8 B load/store (only
// 1/8 of the line is useful -> effective < line bandwidth).
//
// Read/write mix: the access sequence repeats the pattern R reads then W
// writes (--rw 7:3 => 70% reads / 30% writes, 1:1 => 50/50, 1:0 => 100% R,
// 0:1 => 100% W). The op is chosen by position in the sequence, never by
// address, and each block is touched once per pass. Every pass restarts at
// block 0, so in seq mode a given line is always read or always written (the
// last nb % (R+W)*unroll blocks are skipped; negligible). Write-allocate was
// checked with perf: for normal stores ls_any_fills_from_sys.all == lines
// written (one RFO fill per stored line); for --nt stores it is ~0.
//
// Random order: block index = (LCG_state >> 32) * nblocks >> 32 computed in
// registers (4 independent LCG streams) so there is NO index array whose own
// traffic would pollute the measurement. Sampling is with replacement.
//
// Traffic accounting (all GB = 1e9 B, GiB = 2^30 B), per repetition:
//   useful_GBps    = accesses * access_bytes / time   ("program bytes")
//   line_GBps      = accesses * 64 / time              (cache lines touched)
//   est_mem_GBps   = reads*64 + writes*(nt ? 64 : 128) per time. Normal stores
//                    are write-allocate: the line is first read (RFO) and later
//                    written back => 2x DRAM traffic. Only meaningful when the
//                    footprint is far larger than the LLC.
// Timing: threads rendezvous on a barrier, all run until a common deadline,
// aggregate = total bytes / slowest thread time. Per-thread min/max reported.
#include <getopt.h>
#include <immintrin.h>
#include <stdatomic.h>
#include "common.h"

static struct {
    int nthreads, ncpu, cpus[256];
    size_t size, stride;
    int R, W, nt, rnd, a8, thp, nowarm;
    double secs;
    long reps;
} cfg = {.nthreads = 1, .size = 1 << 20, .stride = 64, .R = 1, .W = 0, .thp = 1, .secs = 0.5, .reps = 5};

typedef struct {
    int tid;
    char *buf;
    size_t maplen;
    double elapsed_ns;
    uint64_t accesses, reads, writes;
    uint64_t sink;
} targ_t;

static pthread_barrier_t bar;
static _Atomic double g_t0, g_deadline;
static double g_thp = -1;

// One pass over the buffer. R, W, rnd, nt, a8 are compile-time constants at
// every call site (see DISPATCH), so the mix pattern is fully unrolled.
static inline __attribute__((always_inline)) void pass(char *buf, size_t nb, size_t stride,
        uint64_t *rs, uint64_t *sink, const int R, const int W, const int rnd,
        const int nt, const int a8) {
    const int P = R + W;
    const int U = P >= 8 ? 1 : 8 / P;  // unroll so there are >=8 blocks/iteration
    const int N = P * U;
    __m512i acc[4] = {_mm512_setzero_si512(), _mm512_setzero_si512(),
                      _mm512_setzero_si512(), _mm512_setzero_si512()};
    const __m512i v = _mm512_set1_epi64(0x0123456789abcdefLL);
    uint64_t sacc = 0, st[4] = {rs[0], rs[1], rs[2], rs[3]};
    for (size_t i = 0; i + N <= nb; i += N) {
#pragma GCC unroll 128
        for (int j = 0; j < N; j++) {
            size_t blk;
            if (rnd) {
                st[j & 3] = st[j & 3] * 6364136223846793005ULL + 1442695040888963407ULL;
                blk = (size_t)(((st[j & 3] >> 32) * (uint64_t)nb) >> 32);
            } else {
                blk = i + j;
            }
            char *p = buf + blk * stride;
            if ((j % P) < R) {  // read
                if (a8) sacc += *(volatile uint64_t *)p;
                else acc[j & 3] = _mm512_add_epi64(acc[j & 3], _mm512_load_si512(p));
            } else {            // write
                if (a8) {
                    if (nt) _mm_stream_si64((long long *)p, (long long)i + j);
                    else *(volatile uint64_t *)p = i + j;
                } else {
                    if (nt) _mm512_stream_si512((void *)p, v);
                    else _mm512_store_si512(p, v);
                }
            }
        }
    }
    if (nt && W) _mm_sfence();
    __m512i t = _mm512_add_epi64(_mm512_add_epi64(acc[0], acc[1]), _mm512_add_epi64(acc[2], acc[3]));
    *sink ^= (uint64_t)_mm512_reduce_add_epi64(t) ^ sacc;
    for (int k = 0; k < 4; k++) rs[k] = st[k];
}

typedef void (*pass_fn)(char *, size_t, size_t, uint64_t *, uint64_t *);
#define MK(R_, W_, RND, NT, A8)                                                           \
    static void pass_##R_##_##W_##_##RND##NT##A8(char *b, size_t nb, size_t s,            \
                                                 uint64_t *rs, uint64_t *k) {             \
        pass(b, nb, s, rs, k, R_, W_, RND, NT, A8);                                       \
    }
#define MKALL(R_, W_)                                                                     \
    MK(R_, W_, 0, 0, 0) MK(R_, W_, 0, 0, 1) MK(R_, W_, 0, 1, 0) MK(R_, W_, 0, 1, 1)      \
    MK(R_, W_, 1, 0, 0) MK(R_, W_, 1, 0, 1) MK(R_, W_, 1, 1, 0) MK(R_, W_, 1, 1, 1)
MKALL(1, 0) MKALL(0, 1) MKALL(7, 3) MKALL(1, 1)
#define PICK(R_, W_)                                                                      \
    if (cfg.R == R_ && cfg.W == W_) {                                                     \
        static const pass_fn t[8] = {                                                     \
            pass_##R_##_##W_##_000, pass_##R_##_##W_##_001, pass_##R_##_##W_##_010,       \
            pass_##R_##_##W_##_011, pass_##R_##_##W_##_100, pass_##R_##_##W_##_101,       \
            pass_##R_##_##W_##_110, pass_##R_##_##W_##_111};                              \
        return t[cfg.rnd * 4 + cfg.nt * 2 + cfg.a8];                                      \
    }
static pass_fn pick_pass(void) {
    PICK(1, 0) PICK(0, 1) PICK(7, 3) PICK(1, 1)
    fprintf(stderr, "unsupported --rw %d:%d (supported: 1:0 0:1 7:3 1:1)\n", cfg.R, cfg.W);
    exit(1);
    return NULL;
}

static void *worker(void *arg) {
    targ_t *a = arg;
    if (cfg.ncpu) pin_cpu(cfg.cpus[a->tid % cfg.ncpu]);
    a->buf = alloc_pages(cfg.size, cfg.thp, &a->maplen);
    if (!cfg.nowarm) memset(a->buf, 0x5a, a->maplen);  // first-touch by this thread
    size_t nb = cfg.size / cfg.stride;
    uint64_t rs[4], sink = 0, seed = 0x9e3779b97f4a7c15ULL * (a->tid + 1);
    for (int k = 0; k < 4; k++) rs[k] = xs64(&seed);
    pass_fn fn = pick_pass();
    size_t line_bytes = nb * 64;
    long chunk = (long)((16u << 20) / (line_bytes ? line_bytes : 1));
    if (chunk < 1) chunk = 1;
    int P = cfg.R + cfg.W, U = P >= 8 ? 1 : 8 / P, N = P * U;  // same as in pass()
    uint64_t per_pass = (nb / N) * N;
    uint64_t per_pass_r = (nb / N) * U * cfg.R, per_pass_w = per_pass - per_pass_r;

    if (!cfg.nowarm) fn(a->buf, nb, cfg.stride, rs, &sink);  // warm caches / TLB
    pthread_barrier_wait(&bar);  // INIT: buffers allocated, faulted, warmed
    for (long rep = 0; rep < cfg.reps; rep++) {
        a->accesses = a->reads = a->writes = 0;
        pthread_barrier_wait(&bar);  // A
        if (a->tid == 0) {
            double t0 = now_ns();
            g_t0 = t0;
            g_deadline = t0 + cfg.secs * 1e9;
        }
        pthread_barrier_wait(&bar);  // B
        double t0 = g_t0, dl = g_deadline, t;
        do {
            for (long c = 0; c < chunk; c++) fn(a->buf, nb, cfg.stride, rs, &sink);
            a->accesses += chunk * per_pass;
            a->reads += chunk * per_pass_r;
            a->writes += chunk * per_pass_w;
            t = now_ns();
        } while (t < dl);
        a->elapsed_ns = t - t0;
        a->sink = sink;
        pthread_barrier_wait(&bar);  // C: main reads results now
        pthread_barrier_wait(&bar);  // D: main done reading
    }
    return NULL;
}

int main(int argc, char **argv) {
    const char *cpus = "4,5,6,7", *ctl = NULL, *ack = NULL, *pat = "seq", *pages = "thp";
    int header = 0;
    static struct option opts[] = {
        {"size", 1, 0, 'z'}, {"threads", 1, 0, 't'}, {"cpus", 1, 0, 'c'},  {"rw", 1, 0, 'm'},
        {"nt", 0, 0, 'n'},   {"pattern", 1, 0, 'p'}, {"stride", 1, 0, 's'}, {"access", 1, 0, 'a'},
        {"pages", 1, 0, 'g'}, {"secs", 1, 0, 'd'},   {"reps", 1, 0, 'r'},   {"nowarm", 0, 0, 'w'},
        {"header", 0, 0, 'H'}, {"ctl", 1, 0, 'T'},   {"ack", 1, 0, 'A'},    {0, 0, 0, 0}};
    int c;
    while ((c = getopt_long(argc, argv, "", opts, NULL)) != -1) {
        switch (c) {
        case 'z': cfg.size = strtoull(optarg, NULL, 0); break;
        case 't': cfg.nthreads = atoi(optarg); break;
        case 'c': cpus = optarg; break;
        case 'm': if (sscanf(optarg, "%d:%d", &cfg.R, &cfg.W) != 2) return 1; break;
        case 'n': cfg.nt = 1; break;
        case 'p': pat = optarg; break;
        case 's': cfg.stride = strtoull(optarg, NULL, 0); break;
        case 'a': cfg.a8 = atoi(optarg) == 8; break;
        case 'g': pages = optarg; break;
        case 'd': cfg.secs = atof(optarg); break;
        case 'r': cfg.reps = atol(optarg); break;
        case 'w': cfg.nowarm = 1; break;
        case 'H': header = 1; break;
        case 'T': ctl = optarg; break;
        case 'A': ack = optarg; break;
        default: return 1;
        }
    }
    cfg.rnd = strcmp(pat, "rand") == 0;
    cfg.thp = strcmp(pages, "4k") != 0;
    cfg.ncpu = parse_cpus(cpus, cfg.cpus, 256);
    if (cfg.stride < 64 || cfg.stride % 64 || cfg.size < cfg.stride * 64) {
        fprintf(stderr, "stride must be a multiple of 64 and size >= 64*stride\n");
        return 1;
    }
    char cpulabel[512] = "";
    for (int i = 0; i < cfg.ncpu; i++)
        snprintf(cpulabel + strlen(cpulabel), 16, "%s%d", i ? "+" : "", cfg.cpus[i]);
    if (!cfg.ncpu) strcpy(cpulabel, "unpinned");

    pass_fn probe = pick_pass(); (void)probe;
    pthread_barrier_init(&bar, NULL, cfg.nthreads + 1);  // workers + this thread
    pthread_t th[256];
    targ_t ta[256];
    memset(ta, 0, sizeof ta);
    for (int i = 0; i < cfg.nthreads; i++) {
        ta[i].tid = i;
        pthread_create(&th[i], NULL, worker, &ta[i]);
    }
    if (header)
        puts("threads,cpus,rw,nt,pattern,stride,access,pages,size_per_thread,thp_frac,rep,seconds,"
             "useful_GBps,useful_GiBps,line_GBps,est_mem_GBps,thr_min_GBps,thr_max_GBps,prefault");
    ctl_open(ctl, ack);
    pthread_barrier_wait(&bar);  // INIT: workers finished init + warm-up
    {   // THP check after all buffers are faulted in (workers published bufs).
        char *bufs[256]; size_t lens[256];
        for (int i = 0; i < cfg.nthreads; i++) { bufs[i] = ta[i].buf; lens[i] = ta[i].maplen; }
        g_thp = thp_fraction(bufs, lens, cfg.nthreads);
    }
    ctl_cmd("enable");
    int acc = cfg.a8 ? 8 : 64;
    for (long rep = 0; rep < cfg.reps; rep++) {
        pthread_barrier_wait(&bar);  // start rendezvous (A)
        pthread_barrier_wait(&bar);  // deadline published (B)
        pthread_barrier_wait(&bar);  // all finished (C)
        double tmax = 0, useful = 0, line = 0, mem = 0, tmin_bw = 1e30, tmax_bw = 0;
        for (int i = 0; i < cfg.nthreads; i++) {
            double e = ta[i].elapsed_ns;
            if (e > tmax) tmax = e;
            double bw = ta[i].accesses * (double)acc / e;
            if (bw < tmin_bw) tmin_bw = bw;
            if (bw > tmax_bw) tmax_bw = bw;
            useful += ta[i].accesses * (double)acc;
            line += ta[i].accesses * 64.0;
            mem += ta[i].reads * 64.0 + ta[i].writes * (cfg.nt ? 64.0 : 128.0);
        }
        printf("%d,%s,%d:%d,%d,%s,%zu,%d,%s,%zu,%.3f,%ld,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%d\n",
               cfg.nthreads, cpulabel, cfg.R, cfg.W, cfg.nt, pat, cfg.stride, acc, pages,
               cfg.size, g_thp, rep, tmax / 1e9, useful / tmax, useful / tmax / 1.073741824,
               line / tmax, mem / tmax, tmin_bw, tmax_bw, !cfg.nowarm);
        fflush(stdout);
        pthread_barrier_wait(&bar);  // D: release workers to next rep
    }
    ctl_cmd("disable");
    uint64_t s = 0;
    for (int i = 0; i < cfg.nthreads; i++) { pthread_join(th[i], NULL); s ^= ta[i].sink; }
    if (s == 0x1234) fprintf(stderr, "sink\n");
    return 0;
}
