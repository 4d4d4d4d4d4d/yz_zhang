#!/bin/bash
# SessionStart hook for Claude Code on the web.
#
# Installs the npu_sim package together with its dev dependencies so that the
# test suite (pytest) is ready as soon as the remote session starts. Runs
# synchronously: the session waits for this to finish, so no command can race
# ahead of dependency installation.
set -euo pipefail

# Web sessions only. Local sessions manage their own environments.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-.}"

# Best-effort pip upgrade; the system pip may be distro-managed and refuse to
# uninstall, which must not abort the hook.
python -m pip install --upgrade pip || true

# Editable install reflects source edits without reinstalling; the [dev] extra
# pulls in pytest / pytest-cov / import-linter. Idempotent and benefits from the
# cached container layer on subsequent runs.
python -m pip install -e ".[dev]"
