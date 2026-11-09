#!/bin/sh
set -eu
: "${QWEN_PHONE_SERIAL:?Set QWEN_PHONE_SERIAL to the authorized adb device serial}"
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ZIG="$ROOT/tools/zig/ziglang/zig"
[ -x "$ZIG" ] || { echo 'Missing isolated Zig 0.14.1 toolchain under tools/zig/ziglang' >&2; exit 1; }
[ "$("$ZIG" version)" = 0.14.1 ] || exit 1
mkdir -p "$ROOT/build"
"$ZIG" cc -target aarch64-linux-android -shared -nostdlib -fPIC -O2 -s "$ROOT/native/map-staging.c" -o "$ROOT/build/map-staging.so"
"$ROOT/tools/platform-tools/adb" -s "${QWEN_PHONE_SERIAL}" push "$ROOT/build/map-staging.so" /data/local/tmp/qwen-phone/map-staging.so.new
"$ROOT/tools/platform-tools/adb" -s "${QWEN_PHONE_SERIAL}" shell mv /data/local/tmp/qwen-phone/map-staging.so.new /data/local/tmp/qwen-phone/map-staging.so
