/* perfcyc.h - user-space core-cycle counter via perf_event_open (no root needed with
 * perf_event_paranoid<=2 because kernel/hypervisor cycles are excluded).
 * Design choice (documented in README): cycles-per-element uses the *measured* core-clock
 * cycles (PERF_COUNT_HW_CPU_CYCLES) of the pinned thread over each timed sample, NOT the TSC,
 * because boost frequency varies.  Effective frequency = cycles / elapsed_ns is also reported.
 * If the counter cannot be opened, cyc_read() returns -1 and derived columns are NaN. */
#ifndef PERFCYC_H
#define PERFCYC_H
#define _GNU_SOURCE
#include <linux/perf_event.h>
#include <stdint.h>
#include <string.h>
#include <sys/syscall.h>
#include <unistd.h>

static int cyc_fd = -1;

static inline void cyc_open(void)
{
    struct perf_event_attr pe;
    memset(&pe, 0, sizeof pe);
    pe.type = PERF_TYPE_HARDWARE;
    pe.size = sizeof pe;
    pe.config = PERF_COUNT_HW_CPU_CYCLES;
    pe.exclude_kernel = 1;
    pe.exclude_hv = 1;
    cyc_fd = (int)syscall(SYS_perf_event_open, &pe, 0, -1, -1, 0);
}

static inline int64_t cyc_read(void)
{
    uint64_t v;
    if (cyc_fd < 0 || read(cyc_fd, &v, sizeof v) != (ssize_t)sizeof v) return -1;
    return (int64_t)v;
}
#endif
