#!/usr/bin/env bash
# DEP-030 备份：Postgres 全量 + 存证链 head 快照。
#
#   ./deploy/backup.sh                # 手动
#   0 3 * * *  /srv/app/deploy/backup.sh   # crontab 每日 3 点
#
# 存证链 head 单独存一份的理由：它是「历史未被篡改」的对外可公示锚点。
# 只备份数据库的话，一旦被篡改后再备份，你手里就没有能反驳的独立证据了。
set -euo pipefail

cd "$(dirname "$0")"
set -a; source .env; set +a

BACKUP_DIR="${BACKUP_DIR:-./backups}"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$BACKUP_DIR"

DUMP="$BACKUP_DIR/db-$STAMP.sql.gz"
echo "导出数据库 → $DUMP"
docker compose -f docker-compose.prod.yml --env-file .env exec -T db \
  pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --clean --if-exists \
  | gzip -9 > "$DUMP"

HEAD="$BACKUP_DIR/anchor-head-$STAMP.json"
echo "快照存证链 head → $HEAD"
docker compose -f docker-compose.prod.yml --env-file .env exec -T api python - <<'PY' > "$HEAD" || echo '{"error":"anchor head unavailable"}' > "$HEAD"
import json

from app.core.db import SessionLocal
from app.modules.anchor import service as anchor

with SessionLocal() as db:
    print(json.dumps(anchor.verify_chain(db), ensure_ascii=False, default=str))
PY

echo "清理 ${KEEP_DAYS} 天前的备份"
find "$BACKUP_DIR" -name 'db-*.sql.gz' -mtime "+$KEEP_DAYS" -delete
find "$BACKUP_DIR" -name 'anchor-head-*.json' -mtime "+$KEEP_DAYS" -delete

echo "完成：$(ls -lh "$DUMP" | awk '{print $5}')"
