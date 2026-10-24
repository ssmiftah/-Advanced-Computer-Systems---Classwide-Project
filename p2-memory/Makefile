CC      ?= gcc
CFLAGS  ?= -O3 -march=native -Wall -Wextra
LDLIBS  := -lpthread
BIN     := bin
PROGS   := latency bandwidth mlp kernel_miss tlb
TARGETS := $(addprefix $(BIN)/,$(PROGS))

all: $(TARGETS)

# latency.c was originally built with -O2; keep that so its sanity numbers stay comparable.
$(BIN)/latency: src/latency.c src/common.h | $(BIN)
	$(CC) -O2 -march=native -Wall -Wextra -o $@ $< $(LDLIBS)

$(BIN)/%: src/%.c src/common.h | $(BIN)
	$(CC) $(CFLAGS) -o $@ $< $(LDLIBS)

$(BIN):
	mkdir -p $@

clean:
	rm -rf $(BIN)
.PHONY: all clean
