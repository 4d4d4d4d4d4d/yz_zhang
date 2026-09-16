#!/usr/bin/env bash
# DEP-070 一键部署：起栈 → 迁移 → **全链路验收** → 打印结论。
#
#   ./deploy/oneclick.sh                    # local  ：开发栈（SQLite），零配置
#   ./deploy/oneclick.sh --mode staging     # staging：prod 形态 + Postgres，允许 mock 供应商
#   ./deploy/oneclick.sh --mode prod        # prod   ：完整上线红线自检，一条不过就中止
#   ./deploy/oneclick.sh --verify-only      # 只对已在跑的服务跑验收
#
# **这个脚本以「验收通过」结束，而不是以「容器起来了」结束。**
# 起来了不等于能用：这套系统踩过的坑——验证码没有钥匙孔、被告席没有麦克风、
# requirements 里没有 Postgres 驱动——全都是「容器起来了但服务不可用」。
# 所以最后一步永远是 scripts/acceptance.py，它不过，这次部署就算失败。
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$PWD"
MODE="local"
VERIFY_ONLY=0
SCALE=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode) MODE="$2"; shift 2 ;;
    --scale) SCALE="$2"; shift 2 ;;
    --verify-only) VERIFY_ONLY=1; shift ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "未知参数：$1" >&2; exit 2 ;;
  esac
done

case "$MODE" in local|staging|prod) ;; *) echo "--mode 只能是 local/staging/prod" >&2; exit 2 ;; esac

say()  { printf '\n\033[1m▶ %s\033[0m\n' "$1"; }
die()  { printf '\033[31m✗ %s\033[0m\n' "$1" >&2; exit 1; }

need() { command -v "$1" >/dev/null 2>&1 || die "缺少 $1，请先安装"; }

API_BASE="${PLATFORM_API_BASE:-}"

# ---------------------------------------------------------------- 起栈
if (( ! VERIFY_ONLY )); then
  need docker
  docker compose version >/dev/null 2>&1 || die "需要 docker compose v2"

  if [[ "$MODE" == "local" ]]; then
    say "启动开发栈（SQLite 单副本）"
    docker compose up -d --build
    API_BASE="${API_BASE:-http://localhost:8000}"
  else
    [[ -f deploy/.env ]] || {
      say "生成 deploy/.env（从模板）"
      cp deploy/.env.example deploy/.env
      # 只替换占位密钥；供应商与证书必须由人来填，脚本不代劳
      for key in PLATFORM_JWT_SECRET PLATFORM_JOB_TOKEN; do
        secret="$(openssl rand -hex 32)"
        sed -i.bak "s|^${key}=.*|${key}=${secret}|" deploy/.env
      done
      pw="$(openssl rand -hex 24)"
      sed -i.bak "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=${pw}|" deploy/.env
      rm -f deploy/.env.bak
      echo "  已生成随机密钥。**供应商、CORS 域名、TLS 证书仍需你填**。"
    }
    if [[ "$MODE" == "staging" ]]; then
      say "启动预发栈（Postgres + 多副本形态，允许 mock 供应商）"
      echo "  ⚠️  staging 用 ALLOW_INSECURE=1 跳过上线红线——**切勿接真实用户**。"
      ALLOW_INSECURE=1 ./deploy/up.sh --scale "$SCALE"
    else
      say "启动生产栈（完整上线红线自检）"
      ./deploy/up.sh --scale "$SCALE"
    fi
    API_BASE="${API_BASE:-http://localhost:${WEB_HTTP_PORT:-80}}"
  fi
fi

# ---------------------------------------------------------------- 等就绪
say "等待就绪（/readyz）"
for i in $(seq 1 60); do
  if curl -sf "$API_BASE/readyz" >/dev/null 2>&1; then echo "  就绪：$API_BASE"; break; fi
  [[ "$i" == "60" ]] && die "60 秒内没有就绪。看日志：docker compose logs api --tail=50"
  sleep 2
done

# ---------------------------------------------------------------- 全链路验收
say "全链路验收（scripts/acceptance.py）"
JOB_TOKEN="${PLATFORM_JOB_TOKEN:-dev-job-token-change-me}"
if [[ -f deploy/.env ]]; then
  JOB_TOKEN="$(grep -E '^PLATFORM_JOB_TOKEN=' deploy/.env | cut -d= -f2- || echo "$JOB_TOKEN")"
fi

run_acceptance() {
  if (( VERIFY_ONLY )) || [[ "$MODE" == "local" ]] && [[ -d server ]] && command -v python3 >/dev/null; then
    ( cd server && PLATFORM_API_BASE="$API_BASE" PLATFORM_JOB_TOKEN="$JOB_TOKEN" \
        python3 -m scripts.acceptance )
  else
    # 容器里跑：不依赖宿主机有 Python 与依赖
    docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env exec -T api \
      env PLATFORM_API_BASE="http://localhost:8000" PLATFORM_JOB_TOKEN="$JOB_TOKEN" \
      python -m scripts.acceptance
  fi
}

if run_acceptance; then
  say "部署完成且验收通过"
  cat <<EOF
  API   : $API_BASE
  文档  : $API_BASE/docs   （prod 下应为 404，这是有意的）
  指标  : $API_BASE/metrics 与 /jobz  需 X-Job-Token，且只应内网可达

  下一步：
    1. 配 cron 调度：  cd server && python -m scripts.cron        （15 个 job）
    2. 配告警接收端：  deploy/alerts.prom.yml —— 先跑 promtool check rules
    3. 首次备份演练：  ./deploy/backup.sh && ./deploy/restore.sh <备份文件>
EOF
else
  die "验收未通过——**不要对外开放**。上面列出的失败项就是原因。
     容器起来了不等于服务能用；这个脚本刻意不把「起来了」当成成功。"
fi
