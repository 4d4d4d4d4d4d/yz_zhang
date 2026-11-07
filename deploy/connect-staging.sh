#!/usr/bin/env bash
# Leave running while using the private server deployment.
set -euo pipefail
exec ssh -i "${OPC_SSH_KEY:-$HOME/.ssh/id_ed25519}" \
  -p "${OPC_SSH_PORT:-22}" -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -N \
  -L 127.0.0.1:18080:127.0.0.1:18080 "${OPC_SSH_HOST:-root@192.227.211.5}"
