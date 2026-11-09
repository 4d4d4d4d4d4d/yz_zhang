#!/bin/sh
# Read-only device capability probe. No app installs or setting changes.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ADB="$ROOT/tools/platform-tools/adb"
if [ ! -x "$ADB" ]; then
  echo "Missing Android platform-tools: $ADB" >&2
  exit 1
fi
"$ADB" devices -l
COUNT=$("$ADB" devices | awk 'NR>1 && $2=="device" {n++} END {print n+0}')
if [ "$COUNT" -ne 1 ]; then
  echo "Expected exactly one authorized Android device; found $COUNT. Enable USB debugging and authorize this computer." >&2
  exit 2
fi
SERIAL=$("$ADB" devices | awk 'NR>1 && $2=="device" {print $1}')
mkdir -p "$ROOT/reports"
"$ADB" -s "$SERIAL" shell '
  echo "=== Device ==="
  for p in ro.product.manufacturer ro.product.model ro.product.device ro.soc.manufacturer ro.soc.model ro.board.platform ro.product.cpu.abi ro.build.version.release ro.build.version.sdk; do
    echo "$p=$(getprop "$p")"
  done
  echo "=== Memory ==="
  head -5 /proc/meminfo
  echo "=== Storage ==="
  df -h /data/local/tmp /sdcard
  echo "=== CPU features ==="
  cat /proc/cpuinfo
  echo "=== CPU policies ==="
  for p in /sys/devices/system/cpu/cpufreq/policy*; do
    echo "$p"
    cat "$p/related_cpus" "$p/cpuinfo_max_freq" "$p/scaling_governor" 2>/dev/null
  done
  echo "=== NPU interfaces ==="
  ls -l /dev/*fastrpc* /dev/*adsprpc* /vendor/lib64/*[Ff]astrpc* /vendor/lib64/*[Aa]dsprpc* /vendor/lib64/libQnn* /vendor/dsp/* /vendor/lib/rfsa/adsp/* 2>/dev/null
  echo "=== SELinux ==="
  getenforce
' > "$ROOT/reports/device.txt"
cat "$ROOT/reports/device.txt"
