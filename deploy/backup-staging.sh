#!/usr/bin/env bash
# Run on the server. Database and uploads are both needed for recovery.
set -euo pipefail
cd "$(dirname "$0")"
umask 077
mkdir -p backups
stamp=$(date -u +%Y%m%dT%H%M%SZ)
compose=(docker compose --env-file .env.staging.local -f docker-compose.staging.yml)
# Pause writers for a consistent database + files snapshot.
"${compose[@]}" stop worker api
trap '"${compose[@]}" start api worker >/dev/null' EXIT
"${compose[@]}" exec -T db pg_dump -U taskplat -d taskplat -Fc > "backups/$stamp.dump.tmp"
"${compose[@]}" run --rm --no-deps --entrypoint tar api -C /srv/data -czf - uploads > "backups/$stamp.uploads.tar.gz.tmp"
"${compose[@]}" exec -T db pg_restore --list < "backups/$stamp.dump.tmp" >/dev/null
tar -tzf "backups/$stamp.uploads.tar.gz.tmp" >/dev/null
mv "backups/$stamp.dump.tmp" "backups/$stamp.dump"
mv "backups/$stamp.uploads.tar.gz.tmp" "backups/$stamp.uploads.tar.gz"
echo "Backup complete: backups/$stamp.*"
