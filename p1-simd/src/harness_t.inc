/* harness_t.inc - type-generic benchmark body, included once per element type from main.c.
 * Expects TYP, SFX, IS_FP (1 for float types), EPS (unit-roundoff-scale epsilon). */
#define FN(name) CATX2(name, SFX)

typedef struct { TYP *x, *y, *z; uint32_t *idx; } FN(buf);

typedef struct {
    void (*saxpy)(size_t, TYP, const TYP *restrict, TYP *restrict);
    TYP (*dot)(size_t, const TYP *restrict, const TYP *restrict);
    void (*mul)(size_t, const TYP *restrict, const TYP *restrict, TYP *restrict);
    void (*stencil)(size_t, TYP, TYP, TYP, const TYP *restrict, TYP *restrict);
    void (*saxpy_s)(size_t, size_t, TYP, const TYP *restrict, TYP *restrict);
    TYP (*dot_s)(size_t, size_t, const TYP *restrict, const TYP *restrict);
    void (*saxpy_g)(size_t, TYP, const TYP *restrict, const uint32_t *restrict, TYP *restrict);
    TYP (*dot_g)(size_t, const TYP *restrict, const uint32_t *restrict, const TYP *restrict);
} FN(kset);

#define KFN(P, k) CATX3(P, k, SFX)
static const FN(kset) FN(KS_K) = {KFN(, saxpy), KFN(, dot), KFN(, mul), KFN(, stencil),
                                  KFN(, saxpy_stride), KFN(, dot_stride),
                                  KFN(, saxpy_gather), KFN(, dot_gather)};
static const FN(kset) FN(KS_R) = {KFN(ref_, saxpy), KFN(ref_, dot), KFN(ref_, mul),
                                  KFN(ref_, stencil), KFN(ref_, saxpy_stride),
                                  KFN(ref_, dot_stride), KFN(ref_, saxpy_gather),
                                  KFN(ref_, dot_gather)};
#undef KFN

#if IS_FP
#define CA ((TYP)1e-5) /* small so repeated in-place SAXPY stays bounded (grows linearly) */
#define CS_A ((TYP)0.25)
#define CS_B ((TYP)0.5)
#define CS_C ((TYP)0.25)
#else
#define CA ((TYP)3u)
#define CS_A ((TYP)3u)
#define CS_B ((TYP)5u)
#define CS_C ((TYP)7u)
#endif

static void FN(fill)(TYP *p, size_t n, uint64_t seed)
{
    uint64_t s = seed;
    for (size_t i = 0; i < n; i++) {
        uint64_t r = splitmix(&s);
#if IS_FP
        /* magnitude in [0.5,1), random sign: no zeros/denormals, zero-mean (keeps dot sums small) */
        double m = 0.5 + 0.5 * (double)(r >> 11) * 0x1p-53;
        p[i] = (TYP)((r & 1) ? m : -m);
#else
        p[i] = (TYP)(r >> 32) | 1u;
#endif
    }
}

static inline size_t FN(xi)(const cfg_t *c, const FN(buf) *b, size_t i)
{
    return c->var == V_STRIDE ? i * c->stride : c->var == V_GATHER ? b->idx[i] : i;
}

/* Run the selected kernel K times; returns the sum of the dot results (0 for non-reductions) so
 * the caller can consume it.  Switch is outside the loops so it adds no per-call overhead. */
static TYP FN(reps)(const FN(kset) *k, const cfg_t *c, const FN(buf) *b, size_t K)
{
    TYP s = 0;
    const size_t n = c->n, st = c->stride;
    switch (c->kid * 3 + c->var) {
    case 0: for (size_t r = 0; r < K; r++) k->saxpy(n, CA, b->x, b->y); break;
    case 1: for (size_t r = 0; r < K; r++) k->saxpy_s(n, st, CA, b->x, b->y); break;
    case 2: for (size_t r = 0; r < K; r++) k->saxpy_g(n, CA, b->x, b->idx, b->y); break;
    case 3: for (size_t r = 0; r < K; r++) s += k->dot(n, b->x, b->y); break;
    case 4: for (size_t r = 0; r < K; r++) s += k->dot_s(n, st, b->x, b->y); break;
    case 5: for (size_t r = 0; r < K; r++) s += k->dot_g(n, b->x, b->idx, b->y); break;
    case 6: for (size_t r = 0; r < K; r++) k->mul(n, b->x, b->y, b->z); break;
    case 9: for (size_t r = 0; r < K; r++) k->stencil(n, CS_A, CS_B, CS_C, b->x, b->y); break;
    default: die("unsupported kernel/variant combination");
    }
    return s;
}

static void FN(mismatch)(const cfg_t *c, size_t i, double got, double ref, double tol)
{
    fprintf(stderr, "CORRECTNESS FAILURE build=%s kernel=%s type=%s variant=%s n=%zu stride=%zu "
            "i=%zu got=%.9g ref=%.9g tol=%.3g\n", g_build, c->kname, c->tname, c->vname, c->n,
            c->stride, i, got, ref, tol);
    exit(3);
}

/* Compare the kernel under test with the scalar reference on fresh data.
 * Elementwise kernels: the only legitimate difference is FMA contraction (one fewer rounding) in
 * the vector builds, so |got-ref| <= 4*EPS*(|ref| + sum|terms|); mul has a single rounding so it
 * must match exactly; integers must match exactly (wrap-around arithmetic is associative).
 * dot: reduction order differs, so compare both against a long-double sum of exact products with
 * tol = 4*EPS*sqrt(n)*sqrt(sum p_i^2), i.e. a few times the random-walk rounding-error estimate
 * (data are zero-mean, so partial sums behave like a random walk; the rigorous n*eps*sum|p| bound
 * is vacuous at large n).  Integer dot is exact. */
static void FN(check)(const cfg_t *c, const FN(buf) *b, size_t ylen)
{
    const size_t n = c->n;
    if (c->kid == K_DOT) {
#if IS_FP
        long double ref = 0, sq = 0;
        for (size_t i = 0; i < n; i++) {
            long double p = (long double)b->x[FN(xi)(c, b, i)] * (long double)b->y[i];
            ref += p; sq += p * p;
        }
        TYP got = FN(reps)(&FN(KS_K), c, b, 1);
        TYP rsc = FN(reps)(&FN(KS_R), c, b, 1);
        long double tol = 4.0L * EPS * sqrtl((long double)n) * sqrtl(sq) + 1e-30L;
        if (fabsl((long double)got - ref) > tol) FN(mismatch)(c, 0, got, (double)ref, (double)tol);
        if (fabsl((long double)rsc - ref) > tol) FN(mismatch)(c, 0, rsc, (double)ref, (double)tol);
#else
        TYP ref = 0;
        for (size_t i = 0; i < n; i++) ref += b->x[FN(xi)(c, b, i)] * b->y[i];
        TYP got = FN(reps)(&FN(KS_K), c, b, 1);
        if (got != ref) FN(mismatch)(c, 0, got, ref, 0);
#endif
        return;
    }
    FN(buf) rb = *b;
    TYP *ry = xalloc(ylen * sizeof(TYP), 0, 0, &(void *){0});
    TYP *rz = xalloc(ylen * sizeof(TYP), 0, 0, &(void *){0});
    memcpy(ry, b->y, ylen * sizeof(TYP));
    if (b->z) memcpy(rz, b->z, ylen * sizeof(TYP));
    rb.y = ry; rb.z = b->z ? rz : NULL;
    FN(reps)(&FN(KS_R), c, &rb, 1);
    FN(reps)(&FN(KS_K), c, b, 1);
    const TYP *got = c->kid == K_MUL ? b->z : b->y;
    const TYP *ref = c->kid == K_MUL ? rz : ry;
    for (size_t i = 0; i < ylen; i++) {
#if IS_FP
        double term = 0;
        if (c->kid == K_SAXPY) term = fabs((double)CA * (double)b->x[FN(xi)(c, b, i)]);
        else if (c->kid == K_STENCIL && i > 0 && i + 1 < n)
            term = fabs((double)CS_A * b->x[i - 1]) + fabs((double)CS_B * b->x[i]) +
                   fabs((double)CS_C * b->x[i + 1]);
        double tol = (c->kid == K_MUL) ? 0.0 : 4.0 * EPS * (fabs((double)ref[i]) + term);
        if (fabs((double)got[i] - (double)ref[i]) > tol)
            FN(mismatch)(c, i, got[i], ref[i], tol);
#else
        if (got[i] != ref[i]) FN(mismatch)(c, i, got[i], ref[i], 0);
#endif
    }
    free(ry); free(rz);
}

static void FN(bench)(cfg_t *c)
{
    const size_t n = c->n, sz = sizeof(TYP);
    if (c->kid == K_STENCIL && n < 3) die("stencil needs n>=3");
    size_t xlen = c->var == V_STRIDE ? n * c->stride : n;
    void *bx, *by, *bz = NULL, *bi = NULL;
    FN(buf) b = {0};
    /* distinct 64B-multiple pads (17 and 34 lines) avoid 4K-aliasing between x, y, z; the
     * requested byte offset is added on top. */
    b.x = xalloc(xlen * sz, c->off[0], 0, &bx);
    b.y = xalloc(n * sz, c->off[1], 17 * 64, &by);
    if (c->kid == K_MUL) b.z = xalloc(n * sz, c->off[2], 34 * 64, &bz);
    if (c->var == V_GATHER) {
        b.idx = xalloc(n * 4, 0, 51 * 64, &bi);
        build_idx(b.idx, n, c->gather, c->seed + 99);
    }
    FN(fill)(b.x, xlen, c->seed + 1);
    FN(fill)(b.y, n, c->seed + 2);
    if (b.z) FN(fill)(b.z, n, c->seed + 3);

    if (c->check) FN(check)(c, &b, n);

    /* calibrate K so one timed sample lasts >= min_ms (also serves as warm-up) */
    TYP sink = 0;
    size_t K = 1;
    for (;;) {
        double t0 = now_ns();
        sink += FN(reps)(&FN(KS_K), c, &b, K);
        double dt = now_ns() - t0;
        if (dt >= c->min_ms * 1e6) break;
        double scale = c->min_ms * 1e6 * 1.2 / (dt > 1000 ? dt : 1000);
        K = (size_t)((double)K * (scale < 2 ? 2 : scale)) + 1;
    }
    sink += FN(reps)(&FN(KS_K), c, &b, K); /* one more warm run at final K */

    double flops, bytes;
    kernel_cost(c, sz, &flops, &bytes);
    size_t narr = c->kid == K_MUL ? 3 : 2;
    for (int s = 0; s < c->samples; s++) {
        int64_t c0 = cyc_read();
        double t0 = now_ns();
        sink += FN(reps)(&FN(KS_K), c, &b, K);
        double t1 = now_ns();
        int64_t c1 = cyc_read();
        emit_row(c, sz, narr * n * sz, flops, bytes, K, s, t1 - t0,
                 (c0 < 0 || c1 < 0) ? -1 : c1 - c0, (uintptr_t)b.x & 63, (uintptr_t)b.y & 63);
    }
#if IS_FP
    g_sink += (double)sink;
#else
    g_sink += (double)(uint32_t)sink;
#endif
    free(bx); free(by); free(bz); free(bi);
}
#undef CA
#undef CS_A
#undef CS_B
#undef CS_C
#undef FN
