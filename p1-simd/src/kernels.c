/* kernels.c - code under test.  Compiled once per build (see Makefile) with different flags.
 * Kept in its own translation unit and marked noinline/noipa so the timing harness (main.c)
 * can neither inline the kernels nor constant-fold their arguments. */
#include "kernels.h"

#ifdef __clang__
#define KATTR __attribute__((noinline))
#else
#define KATTR __attribute__((noinline, noipa))
#endif
#define KPFX
#define CATX3(a, b, c) CAT3_(a, b, c)
#define CAT3_(a, b, c) a##b##_##c

#define TYP float
#define SFX f32
#include "kernels_impl.inc"
#undef TYP
#undef SFX
#define TYP double
#define SFX f64
#include "kernels_impl.inc"
#undef TYP
#undef SFX
#define TYP uint32_t
#define SFX i32
#include "kernels_impl.inc"
