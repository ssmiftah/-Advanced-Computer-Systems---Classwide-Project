# Makefile - Project 1 SIMD study.
#   make            build all bin/simd_<build> + bin/membw + bin/peakflops + vectorization reports
#   make clean
# Only kernels.c is compiled per build; main.c/ref.c are compiled once (identical for all builds),
# so any difference between binaries is attributable to the kernel flags alone.
ifeq ($(origin CC),default)
CC := gcc
endif
BUILDS  := scalar scalar_znver5 sse avx2 znver5 znver5_pv512 sse_fm avx2_fm znver5_fm znver5_pv512_fm
WARN    := -Wall -Wextra -std=gnu17
KOPT    := -O3 $(WARN)
FM      := -fassociative-math -fno-signed-zeros -fno-trapping-math

F_scalar        := -fno-tree-vectorize -fno-tree-slp-vectorize
# control: same ISA/tuning as znver5 (FMA contraction, VEX 3-operand) but no vectorization, so
# znver5 vs scalar_znver5 isolates the SIMD-width effect from the scalar-ISA effect
F_scalar_znver5 := -march=znver5 -fno-tree-vectorize -fno-tree-slp-vectorize
F_sse           :=
F_avx2          := -mavx2 -mfma
F_znver5        := -march=znver5
F_znver5_pv512  := -march=znver5 -mprefer-vector-width=512
F_sse_fm        := $(F_sse) $(FM)
F_avx2_fm       := $(F_avx2) $(FM)
F_znver5_fm     := $(F_znver5) $(FM)
F_znver5_pv512_fm := $(F_znver5_pv512) $(FM)

REPDIR := reports
BINS   := $(addprefix bin/simd_,$(BUILDS)) bin/membw bin/peakflops

all: $(BINS) vec-reports

obj/kernels_%.o: src/kernels.c src/kernels.h src/kernels_impl.inc | obj
	$(CC) $(KOPT) $(F_$*) -c $< -o $@
obj/main.o: src/main.c src/harness_t.inc src/kernels.h src/perfcyc.h | obj
	$(CC) -O2 $(WARN) -c $< -o $@
# reference: never vectorized, no FMA contraction, baseline ISA, regardless of build
obj/ref.o: src/ref.c src/kernels.h src/kernels_impl.inc | obj
	$(CC) -O2 $(WARN) -fno-tree-vectorize -fno-tree-slp-vectorize -ffp-contract=off -c $< -o $@
bin/simd_%: obj/main.o obj/ref.o obj/kernels_%.o | bin
	$(CC) $^ -o $@ -lm
bin/membw: src/membw.c src/perfcyc.h | bin
	$(CC) -O3 $(WARN) -march=znver5 -mprefer-vector-width=512 $< -o $@
bin/peakflops: src/peakflops.c src/perfcyc.h | bin
	$(CC) -O3 $(WARN) -march=znver5 $< -o $@
obj bin $(REPDIR):
	mkdir -p $@

# ---- vectorization reports (GCC -fopt-info-vec-*, objdump, flags/versions) ----
REPORTS := $(foreach b,$(BUILDS),$(REPDIR)/$(b).vec-optimized.txt)
vec-reports: $(REPORTS) $(REPDIR)/flags.txt $(REPDIR)/vec_summary.md
$(REPDIR)/%.vec-optimized.txt: src/kernels.c src/kernels_impl.inc | $(REPDIR)
	$(CC) $(KOPT) $(F_$*) -fopt-info-vec-optimized=$@ -c src/kernels.c -o obj/rep_$*.o
	$(CC) $(KOPT) $(F_$*) -fopt-info-vec-missed=$(REPDIR)/$*.vec-missed.txt -c src/kernels.c -o /dev/null
	objdump -d -C --no-show-raw-insn obj/rep_$*.o > $(REPDIR)/$*.objdump.txt
$(REPDIR)/flags.txt: Makefile | $(REPDIR)
	{ $(CC) --version | head -1; clang --version | head -1; echo; \
	  $(foreach b,$(BUILDS),echo "$(b): $(CC) $(KOPT) $(F_$(b)) -c kernels.c";) \
	  echo "harness: $(CC) -O2 $(WARN)"; \
	  echo "reference: $(CC) -O2 $(WARN) -fno-tree-vectorize -fno-tree-slp-vectorize -ffp-contract=off"; \
	  echo "membw: $(CC) -O3 $(WARN) -march=znver5 -mprefer-vector-width=512"; \
	  echo "peakflops: $(CC) -O3 $(WARN) -march=znver5"; } > $@
$(REPDIR)/vec_summary.md: $(REPORTS) scripts/vec_check.py
	bash ../common/pyrun.sh scripts/vec_check.py

# optional: clang's view (loop-vectorize remarks) of the two interesting builds
clang-reports: | $(REPDIR)
	clang $(KOPT) -c src/kernels.c -o /dev/null -Rpass=loop-vectorize -Rpass-missed=loop-vectorize 2> $(REPDIR)/clang_sse.remarks.txt || true
	clang $(KOPT) -march=znver5 -c src/kernels.c -o /dev/null -Rpass=loop-vectorize -Rpass-missed=loop-vectorize 2> $(REPDIR)/clang_znver5.remarks.txt || true
	clang $(KOPT) -march=znver5 -fassociative-math -fno-signed-zeros -fno-trapping-math -c src/kernels.c -o /dev/null -Rpass=loop-vectorize -Rpass-missed=loop-vectorize 2> $(REPDIR)/clang_znver5_fm.remarks.txt || true

clean:
	rm -rf obj bin

.PHONY: all vec-reports clean clang-reports
.PRECIOUS: obj/kernels_%.o
