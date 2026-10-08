#!/usr/bin/env bash
# Issue window depth against a fixed program. The point is to find out
# whether a window full 90+% of the time means "too shallow" or "the
# dependency graph is genuinely serial" -- those look identical from the
# WIN_FULL counter alone and want opposite fixes.
set -u
cd "$(dirname "$0")/.."
# GEN is the generator command line; the program is regenerated per window
# depth because the event-recycling rule targets a specific one. Running a
# program built for a shallower window on a deeper one is a contract
# violation and the testbench says so rather than hanging.
GEN=${GEN:?set GEN to a generator command line}
WINS=${WINS:-"8 16 32"}
PROG=/tmp/npu_win_prog.txt

RTL="rtl/npu_pkg.sv rtl/npu_prim.sv rtl/npu_ecc.sv rtl/npu_buffer.sv \
     rtl/npu_xbar.sv rtl/npu_msgq.sv rtl/npu_sem.sv rtl/npu_opsched.sv \
     rtl/npu_fp.sv rtl/npu_cube.sv rtl/npu_vec.sv rtl/npu_fix.sv \
     rtl/npu_mte.sv rtl/npu_csr.sv rtl/npu_qch.sv rtl/npu_top.sv"

printf '%-5s %9s %9s %8s %8s %8s\n' WIN cycles win_full dep% cred% ord%
for w in $WINS; do
  d=build/win_$w
  verilator --binary -j 4 --timing -Wno-fatal --assert -Irtl -Itb \
    -DNPU_WIN=$w rtl/npu.vlt --Mdir $d --top-module tb_npu_prog \
    $RTL tb/axi_mem.sv tb/tb_npu_prog.sv -o run >/dev/null 2>&1 || {
      printf '%-5s BUILD FAIL\n' "$w"; continue; }
  python3 $GEN --win $w -o "$PROG" >/dev/null 2>&1 || {
    printf '%-5s GEN FAIL\n' "$w"; continue; }
  out=$(./$d/run +prog="$PROG" 2>&1)
  grep -q 'TEST PASSED' <<<"$out" || { printf '%-5s TEST FAIL\n' "$w"; continue; }
  cy=$(sed -n 's/.*STATS cycles=\([0-9]*\).*/\1/p' <<<"$out")
  wf=$(sed -n 's/.*win_full=\([0-9]*\).*/\1/p' <<<"$out")
  sd=$(sed -n 's/.*STALL dependency=\([0-9]*\).*/\1/p' <<<"$out")
  sc=$(sed -n 's/.*credit=\([0-9]*\).*/\1/p'          <<<"$out")
  so=$(sed -n 's/.*ordering=\([0-9]*\).*/\1/p'        <<<"$out")
  printf '%-5s %9s %9s %7s%% %7s%% %7s%%\n' "$w" "$cy" "$wf" \
     $((100*sd/cy)) $((100*sc/cy)) $((100*so/cy))
done
