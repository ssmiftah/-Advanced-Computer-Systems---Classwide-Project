#!/usr/bin/env bash
# Put the machine into a low-noise benchmark state, or restore defaults.
# Usage: sudo common/bench_mode.sh on [--no-boost]
#        sudo common/bench_mode.sh off
# This changes system-wide settings, so it affects all users of the machine.
set -eu
state_file=/tmp/acs_bench_mode_saved

if [[ $EUID -ne 0 ]]; then echo "run with sudo" >&2; exit 1; fi

case "${1:-}" in
  on)
    # Save current settings so "off" restores exactly what was there.
    {
      echo "gov=$(cat /sys/devices/system/cpu/cpufreq/policy0/scaling_governor)"
      echo "boost=$(cat /sys/devices/system/cpu/cpufreq/boost 2>/dev/null || echo na)"
      echo "paranoid=$(cat /proc/sys/kernel/perf_event_paranoid)"
      echo "sched=$(sed -E 's/.*\[(.*)\].*/\1/' /sys/block/nvme0n1/queue/scheduler)"
    } > "$state_file"
    cpupower frequency-set -g performance >/dev/null
    if [[ "${2:-}" == "--no-boost" && -w /sys/devices/system/cpu/cpufreq/boost ]]; then
      echo 0 > /sys/devices/system/cpu/cpufreq/boost
    fi
    # Allow perf to read hardware counters without root.
    echo -1 > /proc/sys/kernel/perf_event_paranoid
    # No I/O scheduler on the NVMe drive: kyber (CachyOS default) throttles queue depth
    # and distorts queue-depth sweeps (see p3-ssd/FINDINGS.md).
    echo none > /sys/block/nvme0n1/queue/scheduler
    echo "bench mode ON (saved previous settings to $state_file)"
    ;;
  off)
    if [[ -f "$state_file" ]]; then source "$state_file"; else gov=powersave boost=1 paranoid=2; fi
    echo "${sched:-kyber}" > /sys/block/nvme0n1/queue/scheduler
    cpupower frequency-set -g "$gov" >/dev/null
    [[ "$boost" != na && -w /sys/devices/system/cpu/cpufreq/boost ]] && echo "$boost" > /sys/devices/system/cpu/cpufreq/boost
    echo "$paranoid" > /proc/sys/kernel/perf_event_paranoid
    echo "bench mode OFF (governor=$gov boost=$boost paranoid=$paranoid nvme0n1 scheduler=${sched:-kyber})"
    ;;
  *) echo "usage: $0 on [--no-boost] | off" >&2; exit 1 ;;
esac
