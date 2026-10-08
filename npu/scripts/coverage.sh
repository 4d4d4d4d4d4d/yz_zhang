#!/usr/bin/env bash
# Line and toggle coverage over the RTL, accumulated across the suite.
#
# Coverage is not a goal in itself, but "every VEC opcode is swept" says
# nothing about whether every path inside each one is taken. This is how
# that claim gets a number.
set -u
cd "$(dirname "$0")/.."
B=build/cov
V=tests/vectors
mkdir -p "$B" "$V"

RTL="rtl/npu_pkg.sv rtl/npu_prim.sv rtl/npu_ecc.sv rtl/npu_buffer.sv \
     rtl/npu_xbar.sv rtl/npu_msgq.sv rtl/npu_sem.sv rtl/npu_opsched.sv \
     rtl/npu_fp.sv rtl/npu_cube.sv rtl/npu_vec.sv rtl/npu_fix.sv \
     rtl/npu_mte.sv rtl/npu_csr.sv rtl/npu_qch.sv rtl/npu_top.sv"

echo "building instrumented testbenches"
for tb in tb_npu_prog tb_ctrl tb_cube; do
  verilator --cc --exe --build -j 2 --timing -Wno-fatal --assert \
    -Irtl -Itb rtl/npu.vlt --coverage-line --coverage-toggle \
    --prefix Vtop --Mdir "$B/$tb" --top-module "$tb" \
    -CFLAGS -O2 $RTL tb/axi_mem.sv "tb/$tb.sv" "$PWD/tb/cov_main.cpp" \
    -o "$tb" >/dev/null 2>&1 \
    || { echo "  build failed: $tb"; exit 1; }
done

rm -f "$B"/*.dat
n=0
collect() {            # collect <tb> [plusarg]
  n=$((n + 1))
  if [ $# -ge 2 ]; then
    "$B/$1/$1" "$2" "+covfile=$PWD/$B/run$n.dat" >/dev/null 2>&1 || true
  else
    "$B/$1/$1"      "+covfile=$PWD/$B/run$n.dat" >/dev/null 2>&1 || true
  fi
}

echo "running"
collect tb_cube
collect tb_ctrl
for g in "gen_random.py -s 1 -n 18" "gen_random.py -s 2 --fp -n 18" \
         "gen_random.py -s 3 -n 40" "gen_gemm.py -M 32 -N 32 -K 64 --kb 32" \
         "gen_gemm.py -M 32 -N 128 -K 128 --kb 64 --fp" \
         "gen_encoder.py -S 32 -d 32 --ff 64" "gen_chain.py -n 32" "gen_dma.py" \
         "gen_random.py -s 9 --fp -n 4 --op recip" \
         "gen_random.py -s 9 --fp -n 4 --op lut" \
         "gen_random.py -s 9 -n 4 --op cvt_i2f"; do
  python3 tools/$g -o "$V/cov.txt" >/dev/null 2>&1
  collect tb_npu_prog "+prog=$PWD/$V/cov.txt"
done

echo "merging $(ls "$B"/run*.dat | wc -l) runs"
verilator_coverage --write "$B/all.dat" "$B"/run*.dat >/dev/null
verilator_coverage --annotate "$B/annotated" --annotate-min 1 "$B/all.dat" \
  >/dev/null 2>&1 || true

python3 scripts/cov_report.py "$B/all.dat"
