#!/bin/sh
set -eu
: "${QWEN_PHONE_SERIAL:?Set QWEN_PHONE_SERIAL to the authorized adb device serial}"
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
JAVA_BIN=${QWEN_JAVA_BIN:-/Applications/PyCharm.app/Contents/jbr/Contents/Home/bin}
mkdir -p "$ROOT/build/agent"
rm -f "$ROOT"/build/agent/*.class
"$JAVA_BIN/javac" --release 8 -Xlint:-options -cp "$ROOT/tools/json.jar:$ROOT/tools/android.jar" -d "$ROOT/build/agent" "$ROOT"/agent/*.java
"$JAVA_BIN/java" -cp "$ROOT/tools/r8.jar" com.android.tools.r8.D8 --min-api 26 --lib "$ROOT/tools/android.jar" --output "$ROOT/build/agent.jar" "$ROOT"/build/agent/*.class
"$ROOT/tools/platform-tools/adb" -s "${QWEN_PHONE_SERIAL}" push "$ROOT/build/agent.jar" /data/local/tmp/qwen-phone/agent.jar.new
"$ROOT/tools/platform-tools/adb" -s "${QWEN_PHONE_SERIAL}" shell mv /data/local/tmp/qwen-phone/agent.jar.new /data/local/tmp/qwen-phone/agent.jar
"$ROOT/tools/platform-tools/adb" -s "${QWEN_PHONE_SERIAL}" push "$ROOT/agent/index.html" /data/local/tmp/qwen-phone/index.html.new
"$ROOT/tools/platform-tools/adb" -s "${QWEN_PHONE_SERIAL}" shell mv /data/local/tmp/qwen-phone/index.html.new /data/local/tmp/qwen-phone/index.html
