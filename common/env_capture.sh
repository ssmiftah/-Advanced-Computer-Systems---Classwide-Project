#!/usr/bin/env bash
# Record the machine/software state alongside each experiment run.
# Usage: common/env_capture.sh <output_file>
set -u
out="${1:-/dev/stdout}"

section() { printf '\n## %s\n' "$1"; }

{
  echo "# Environment capture"
  echo "date: $(date -Iseconds)"
  echo "host: $(hostname)"

  section "CPU"
  lscpu | grep -E 'Model name|Thread\(s\) per core|Core\(s\) per socket|Socket|CPU max MHz|CPU min MHz|L1d|L1i|L2|L3|NUMA node'
  echo "ISA flags: $(grep -o -w -E 'avx512f|avx512vl|avx512bw|avx512dq|avx2|fma|sse4_2' /proc/cpuinfo | sort -u | tr '\n' ' ')"

  section "Frequency / SMT"
  echo "governor (cpu0): $(cat /sys/devices/system/cpu/cpufreq/policy0/scaling_governor 2>/dev/null)"
  echo "boost: $(cat /sys/devices/system/cpu/cpufreq/boost 2>/dev/null || echo n/a)"
  echo "amd_pstate: $(cat /sys/devices/system/cpu/amd_pstate/status 2>/dev/null || echo n/a)"
  echo "epp (cpu0): $(cat /sys/devices/system/cpu/cpufreq/policy0/energy_performance_preference 2>/dev/null || echo n/a)"
  echo "SMT: $(cat /sys/devices/system/cpu/smt/control 2>/dev/null)"

  section "Memory"
  free -h
  echo "THP enabled: $(cat /sys/kernel/mm/transparent_hugepage/enabled)"
  echo "THP defrag: $(cat /sys/kernel/mm/transparent_hugepage/defrag)"
  grep -E 'HugePages_Total|Hugepagesize' /proc/meminfo

  section "OS / tools"
  uname -a
  gcc --version | head -1
  clang --version | head -1
  perf --version 2>/dev/null || echo "perf: missing"
  fio --version 2>/dev/null || echo "fio: missing"
  python3 --version
  echo "perf_event_paranoid: $(cat /proc/sys/kernel/perf_event_paranoid)"

  section "Storage"
  lsblk -o NAME,SIZE,TYPE,MODEL,ROTA,MOUNTPOINTS -e 7
  for q in /sys/block/nvme*/queue; do
    echo "$(basename "$(dirname "$q")") scheduler: $(cat "$q/scheduler")  nr_requests: $(cat "$q/nr_requests")"
  done
  df -h /home | tail -1

  section "Load (noise check)"
  uptime
  echo "logged-in users: $(who | wc -l)"
} > "$out" 2>&1
