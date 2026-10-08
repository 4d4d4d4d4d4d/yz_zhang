#!/usr/bin/env bash
# Burst length x outstanding depth, against a fixed memory latency.
#
# The two substitute for each other: what has to cover the latency is their
# PRODUCT. Run it with LAT=0 as well and the whole table flattens -- a
# zero-latency memory model makes every configuration look equally good and
# hides the only two knobs that matter.
set -u
cd "$(dirname "$0")/.."
PROG=${PROG:-/tmp/npu_sweep_gemm.txt}
LATS=${LATS:-"20"}
BURSTS=${BURSTS:-"1 4 16"}
IDWS=${IDWS:-"0 1 2"}

python3 tools/gen_gemm.py -M 32 -N 64 -K 128 --kb 128 -o "$PROG" >/dev/null

RTL="rtl/npu_pkg.sv rtl/npu_prim.sv rtl/npu_ecc.sv rtl/npu_buffer.sv \
     rtl/npu_xbar.sv rtl/npu_msgq.sv rtl/npu_sem.sv rtl/npu_opsched.sv \
     rtl/npu_fp.sv rtl/npu_cube.sv rtl/npu_vec.sv rtl/npu_fix.sv \
     rtl/npu_mte.sv rtl/npu_csr.sv rtl/npu_qch.sv rtl/npu_top.sv"

printf '%-6s %-7s %-12s %10s %10s %8s\n' lat burst outstanding cycles ideal "MAC%"
for lat in $LATS; do
  for b in $BURSTS; do
    for idw in $IDWS; do
      d=build/sw_${lat}_${b}_${idw}
      verilator --binary -j 4 --timing -Wno-fatal --assert -Irtl -Itb \
        -DNPU_MAX_BURST=$b -DNPU_AXI_IDW=$idw -DMEM_LAT=$lat \
        rtl/npu.vlt --Mdir $d --top-module tb_npu_prog \
        $RTL tb/axi_mem.sv tb/tb_npu_prog.sv -o run >/dev/null 2>&1 || {
          printf '%-6s %-7s %-12s %10s\n' "$lat" "$b" "$((1<<idw))" "BUILD FAIL"
          continue; }
      out=$(./$d/run +prog="$PROG" 2>&1)
      cyc=$(sed -n 's/.*STATS cycles=\([0-9]*\).*/\1/p' <<<"$out")
      ideal=$(sed -n 's/.*ideal_cycles=\([0-9]*\).*/\1/p' <<<"$out")
      st=$(grep -oE 'TEST (PASSED|FAILED)' <<<"$out" | head -1)
      if [ "$st" != "TEST PASSED" ]; then cyc="$cyc($st)"; fi
      pct=$([ -n "$cyc" ] && [ -n "$ideal" ] && echo $((100*ideal/cyc)) || echo "-")
      printf '%-6s %-7s %-12s %10s %10s %7s%%\n' "$lat" "$b" "$((1<<idw))" \
             "$cyc" "$ideal" "$pct"
    done
  done
done
