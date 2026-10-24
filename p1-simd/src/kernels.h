/* kernels.h - declarations for the four SIMD-study kernels (+ stride / gather variants)
 * in three element types.  Two sets exist:
 *   <kernel>_<type>      : the code under test (kernels.c, compiled with a per-build flag set)
 *   ref_<kernel>_<type>  : scalar reference (ref.c, always compiled with vectorization disabled)
 * Types: f32 = float, f64 = double, i32 = uint32_t (unsigned so wrap-around is defined). */
#ifndef KERNELS_H
#define KERNELS_H
#include <stddef.h>
#include <stdint.h>

#define KTYPES(X) X(f32, float) X(f64, double) X(i32, uint32_t)

#define KDECL(P, N, T)                                                                          \
    void P##saxpy_##N(size_t n, T a, const T *restrict x, T *restrict y);                       \
    T P##dot_##N(size_t n, const T *restrict x, const T *restrict y);                           \
    void P##mul_##N(size_t n, const T *restrict x, const T *restrict y, T *restrict z);         \
    void P##stencil_##N(size_t n, T a, T b, T c, const T *restrict x, T *restrict y);           \
    void P##saxpy_stride_##N(size_t n, size_t s, T a, const T *restrict x, T *restrict y);      \
    T P##dot_stride_##N(size_t n, size_t s, const T *restrict x, const T *restrict y);          \
    void P##saxpy_gather_##N(size_t n, T a, const T *restrict x, const uint32_t *restrict idx,  \
                             T *restrict y);                                                    \
    T P##dot_gather_##N(size_t n, const T *restrict x, const uint32_t *restrict idx,            \
                        const T *restrict y);

#define KDECL_K(N, T) KDECL(, N, T)
#define KDECL_R(N, T) KDECL(ref_, N, T)
KTYPES(KDECL_K)
KTYPES(KDECL_R)

#endif
