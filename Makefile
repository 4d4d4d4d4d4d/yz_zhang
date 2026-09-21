# ==========================================================
# NPU build / verification driver
# ==========================================================
VERILATOR ?= verilator
RTL_DIR   := rtl
TB_DIR    := tb
BUILD     := build

RTL := $(RTL_DIR)/npu_pkg.sv      \
       $(RTL_DIR)/npu_prim.sv     \
       $(RTL_DIR)/npu_ecc.sv      \
       $(RTL_DIR)/npu_buffer.sv   \
       $(RTL_DIR)/npu_xbar.sv     \
       $(RTL_DIR)/npu_msgq.sv     \
       $(RTL_DIR)/npu_sem.sv      \
       $(RTL_DIR)/npu_opsched.sv  \
       $(RTL_DIR)/npu_fp.sv       \
       $(RTL_DIR)/npu_cube.sv     \
       $(RTL_DIR)/npu_vec.sv      \
       $(RTL_DIR)/npu_fix.sv      \
       $(RTL_DIR)/npu_mte.sv      \
       $(RTL_DIR)/npu_csr.sv      \
       $(RTL_DIR)/npu_qch.sv      \
       $(RTL_DIR)/npu_top.sv

# testbench support models, compiled with every testbench
TB_LIB := $(TB_DIR)/axi_mem.sv

VFLAGS := --binary -j 4 --timing -Wall -Wno-fatal \
          --assert -Irtl -Itb $(RTL_DIR)/npu.vlt \
          -CFLAGS "-O2"

# every tb/tb_*.sv is a self-checking testbench
TBS  := $(notdir $(basename $(wildcard $(TB_DIR)/tb_*.sv)))

# extra plusargs for a run, e.g. make tb_npu_prog RUNARGS=+prog=foo.txt
RUNARGS ?=

.PHONY: all lint test clean $(TBS)

all: lint

lint: 
	@$(VERILATOR) --lint-only -Wall --timing -Irtl $(RTL_DIR)/npu.vlt \
	   $(RTL) --top-module npu_top

# make tb_foo -> build and run tb/tb_foo.sv
$(TBS): %: $(TB_DIR)/%.sv $(RTL) $(TB_LIB)
	@mkdir -p $(BUILD)
	@$(VERILATOR) $(VFLAGS) --Mdir $(BUILD)/$@ --top-module $@ \
	   $(RTL) $(TB_LIB) $< -o $@ >/dev/null
	@./$(BUILD)/$@/$@ $(RUNARGS)

test:
	@bash scripts/run_tests.sh

clean:
	@rm -rf $(BUILD)
