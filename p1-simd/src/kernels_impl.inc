/* kernels_impl.inc - kernel bodies, included once per element type from kernels.c / ref.c.
 * Expects: TYP (element type), SFX (name suffix), KPFX (name prefix), KATTR.
 * Each hot loop carries a "LOOP:<name>" marker on its for-line; scripts/vec_check.py uses the
 * marker to map compiler vectorization reports (file:line) back to kernels.
 * All pointers are restrict (x, y, z never alias in the harness), so the compiler need not
 * emit runtime alias checks.  Sizes are runtime values, so there is always a loop tail. */
#define KNAME(k) CATX3(KPFX, k, SFX)

/* SAXPY: y[i] = a*x[i] + y[i]   (2 FLOP; read x, read y, write y) */
KATTR void KNAME(saxpy)(size_t n, TYP a, const TYP *restrict x, TYP *restrict y)
{
    for (size_t i = 0; i < n; i++) y[i] = a * x[i] + y[i]; /* LOOP:saxpy */
}

/* dot: s = sum x[i]*y[i]  (2 FLOP).  FP reduction: the compiler may only vectorize it if it is
 * allowed to reassociate (-fassociative-math, implied by -ffast-math). */
KATTR TYP KNAME(dot)(size_t n, const TYP *restrict x, const TYP *restrict y)
{
    TYP s = 0;
    for (size_t i = 0; i < n; i++) s += x[i] * y[i]; /* LOOP:dot */
    return s;
}

/* elementwise multiply: z[i] = x[i]*y[i]  (1 FLOP; read x, read y, write z) */
KATTR void KNAME(mul)(size_t n, const TYP *restrict x, const TYP *restrict y, TYP *restrict z)
{
    for (size_t i = 0; i < n; i++) z[i] = x[i] * y[i]; /* LOOP:mul */
}

/* 3-point stencil: y[i] = a*x[i-1] + b*x[i] + c*x[i+1], i = 1..n-2  (5 FLOP per output) */
KATTR void KNAME(stencil)(size_t n, TYP a, TYP b, TYP c, const TYP *restrict x, TYP *restrict y)
{
    for (size_t i = 1; i + 1 < n; i++) y[i] = a * x[i - 1] + b * x[i] + c * x[i + 1]; /* LOOP:stencil */
}

/* strided: x is read at x[i*s], y is unit stride */
KATTR void KNAME(saxpy_stride)(size_t n, size_t s, TYP a, const TYP *restrict x, TYP *restrict y)
{
    for (size_t i = 0; i < n; i++) y[i] = a * x[i * s] + y[i]; /* LOOP:saxpy_stride */
}
KATTR TYP KNAME(dot_stride)(size_t n, size_t s, const TYP *restrict x, const TYP *restrict y)
{
    TYP acc = 0;
    for (size_t i = 0; i < n; i++) acc += x[i * s] * y[i]; /* LOOP:dot_stride */
    return acc;
}

/* gather-like: x is read at x[idx[i]] */
KATTR void KNAME(saxpy_gather)(size_t n, TYP a, const TYP *restrict x,
                               const uint32_t *restrict idx, TYP *restrict y)
{
    for (size_t i = 0; i < n; i++) y[i] = a * x[idx[i]] + y[i]; /* LOOP:saxpy_gather */
}
KATTR TYP KNAME(dot_gather)(size_t n, const TYP *restrict x, const uint32_t *restrict idx,
                            const TYP *restrict y)
{
    TYP acc = 0;
    for (size_t i = 0; i < n; i++) acc += x[idx[i]] * y[i]; /* LOOP:dot_gather */
    return acc;
}
#undef KNAME
