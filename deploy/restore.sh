#!/usr/bin/env bash
# DEP-031/032 恢复：导入备份 → **强制做一致性校验**（资金四不变量 + 存证链）。
#
#   ./deploy/restore.sh backups/db-20260822T030000Z.sql.gz
#
# 恢复不等于成功。备份可能来自一个已经不平的时刻，或导入过程中断。
# 因此这个脚本在导入后必须跑校验，校验不过就明确报失败——不给人「大概好了」的错觉。
set -euo pipefail

DUMP="${1:-}"
if [[ -z "$DUMP" || ! -f "$DUMP" ]]; then
  echo "用法：./deploy/restore.sh <备份文件.sql.gz>" >&2
  exit 1
fi

cd "$(dirname "$0")"
set -a; source .env; set +a
DUMP_PATH="$(cd "$(dirname "../$DUMP")" 2>/dev/null && pwd)/$(basename "$DUMP")" || DUMP_PATH="$DUMP"

echo "⚠️  即将把当前数据库覆盖为：$DUMP"
read -r -p "确认请输入 yes：" ok
[[ "$ok" == "yes" ]] || { echo "已取消"; exit 1; }

echo "停止 api / worker（避免恢复过程中有写入）…"
docker compose -f docker-compose.prod.yml --env-file .env stop api worker

echo "导入…"
gunzip -c "$DUMP_PATH" | docker compose -f docker-compose.prod.yml --env-file .env \
  exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 >/dev/null

echo "重启并校验…"
docker compose -f docker-compose.prod.yml --env-file .env start api worker
sleep 5

docker compose -f docker-compose.prod.yml --env-file .env exec -T api python - <<'PY'
import sys

from app.core.db import SessionLocal
from app.modules.anchor import service as anchor
from app.modules.risk import service as risk

with SessionLocal() as db:
    money = risk.reconcile(db)
    chain = anchor.verify_chain(db)

print("资金对账:", money.get("ok"), money)
print("存证链:", chain.get("valid"), {k: v for k, v in chain.items() if k != "head"})
if not money.get("ok") or not chain.get("valid"):
    print("恢复后一致性校验未通过——不要对外提供服务，先人工核对。")
    sys.exit(1)
print("恢复完成且一致性校验通过。")
PY
