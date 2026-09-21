#!/usr/bin/env bash
# Build and run the whole suite: unit testbenches, then generated programs
# through the program-driven top-level testbench.
set -u
cd "$(dirname "$0")/.."
pass=0; fail=0; failed=()

run() {   # run <name> <command...>
  local name="$1"; shift
  printf '%-40s ' "$name"
  if out=$("$@" 2>&1) && grep -q 'TEST PASSED' <<<"$out"; then
    echo "PASS"; pass=$((pass+1))
  else
    echo "FAIL"; fail=$((fail+1)); failed+=("$name")
    tail -20 <<<"$out" | sed 's/^/    /'
  fi
}

echo "== lint =="
if make lint >/tmp/npu_lint.log 2>&1; then
  echo "verilator -Wall: clean"
else
  echo "verilator -Wall: FAILED"; sed 's/^/    /' /tmp/npu_lint.log; exit 1
fi

echo
echo "== unit testbenches =="
for tb in tb/tb_*.sv; do
  name=$(basename "$tb" .sv)
  [ "$name" = tb_npu_prog ] && continue
  make "$name" >/tmp/npu_$name.log 2>&1
  run "$name" cat /tmp/npu_$name.log
done

echo
echo "== program-driven tests =="
make tb_npu_prog >/dev/null 2>&1 || { echo "build failed"; exit 1; }
BIN=./build/tb_npu_prog/tb_npu_prog
V=tests/vectors
mkdir -p "$V"

gen_run() {  # gen_run <name> <generator args...>
  local name="$1"; shift
  local f="$V/$name.txt"
  if ! python3 "$@" -o "$f" >/tmp/npu_gen.log 2>&1; then
    printf '%-40s FAIL (generator)\n' "$name"
    fail=$((fail+1)); failed+=("$name"); sed 's/^/    /' /tmp/npu_gen.log
    return
  fi
  run "$name" "$BIN" "+prog=$f"
}

for s in 1 2 3; do
  gen_run "random.int.s$s"  tools/gen_random.py -s "$s" -n 18
  gen_run "random.bf16.s$s" tools/gen_random.py -s "$s" --fp -n 18
done
for op in mov addi muli maxi add sub mul max min brc_r brc_c \
          red_sum red_max lut recip sel seld cvt_f2i; do
  gen_run "vecop.$op" tools/gen_random.py -s 4 --fp -n 4 --op "$op"
done
gen_run "gemm.32x32x64"   tools/gen_gemm.py -M 32 -N 32 -K 64  --kb 32
gen_run "gemm.32x128x128" tools/gen_gemm.py -M 32 -N 128 -K 128 --kb 64
gen_run "gemm.bf16"       tools/gen_gemm.py -M 32 -N 32 -K 64 --kb 64 --fp
gen_run "encoder.32x32"   tools/gen_encoder.py -S 32 -d 32 --ff 64

echo "----------------------------------------------------------"
echo "passed: $pass   failed: $fail"
[ "$fail" -eq 0 ] || { echo "failing: ${failed[*]}"; exit 1; }
