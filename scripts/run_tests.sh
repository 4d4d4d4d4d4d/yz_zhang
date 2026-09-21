#!/usr/bin/env bash
# Build and run every self-checking testbench; summarise pass/fail.
set -u
cd "$(dirname "$0")/.."
pass=0; fail=0; failed=()
for tb in tb/tb_*.sv; do
  name=$(basename "$tb" .sv)
  printf '%-28s ' "$name"
  if out=$(make "$name" 2>&1); then
    if grep -q 'TEST PASSED' <<<"$out"; then
      echo "PASS"; pass=$((pass+1))
    else
      echo "FAIL (no pass marker)"; fail=$((fail+1)); failed+=("$name")
      echo "$out" | tail -20 | sed 's/^/    /'
    fi
  else
    echo "FAIL (build/run error)"; fail=$((fail+1)); failed+=("$name")
    echo "$out" | tail -25 | sed 's/^/    /'
  fi
done
echo "--------------------------------------------"
echo "passed: $pass   failed: $fail"
[ "$fail" -eq 0 ] || { echo "failing: ${failed[*]}"; exit 1; }
