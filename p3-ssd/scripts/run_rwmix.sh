#!/usr/bin/env bash
# Exp 3: R/W mix sweep (100R, 70/30, 50/50, 100W) at fixed bs (RWMIX_BS, default 4k),
# random pattern, QD RWMIX_QD (default 32), direct=1.
source "$(dirname "$0")/common.sh"; common_init "$@"
dflt RWMIX_BS 4k 4k; dflt RWMIX_QD 32 32; dflt RWMIX_LIST "100 70 50 0" "100 70 0"
begin_experiment rwmix
for m in $RWMIX_LIST; do
  if   (( m == 100 )); then run_fio "mix_r100" RW=randread  BS=$RWMIX_BS IODEPTH=$RWMIX_QD RWMIX=100
  elif (( m == 0 ));   then run_fio "mix_r0"   RW=randwrite BS=$RWMIX_BS IODEPTH=$RWMIX_QD RWMIX=0
  else run_fio "mix_r$m" RW=randrw BS=$RWMIX_BS IODEPTH=$RWMIX_QD RWMIX=$m; fi
done
end_experiment
