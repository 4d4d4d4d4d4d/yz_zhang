#!/usr/bin/env bash
# DEP-002 一键部署：先做配置自检，再起栈。
#
#   ./deploy/up.sh            起栈
#   ./deploy/up.sh --scale 3  API 起 3 副本（worker 仍固定 1）
set -euo pipefail

cd "$(dirname "$0")"
COMPOSE_FILE="docker-compose.prod.yml"
ENV_FILE=".env"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "缺少 deploy/.env —— 先执行：cp deploy/.env.example deploy/.env 并逐项填写" >&2
  exit 1
fi

# shellcheck disable=SC1090
set -a; source "$ENV_FILE"; set +a

fail=0
note() { echo "  ✗ $1" >&2; fail=1; }

echo "配置自检（DEP-002）…"
[[ "${PLATFORM_JWT_SECRET:-}" == "CHANGE_ME" || -z "${PLATFORM_JWT_SECRET:-}" ]] \
  && note "PLATFORM_JWT_SECRET 未设置（openssl rand -hex 32）"
[[ "${PLATFORM_JOB_TOKEN:-}" == "CHANGE_ME" || -z "${PLATFORM_JOB_TOKEN:-}" ]] \
  && note "PLATFORM_JOB_TOKEN 未设置"
[[ "${POSTGRES_PASSWORD:-}" == "CHANGE_ME_STRONG_PASSWORD" || -z "${POSTGRES_PASSWORD:-}" ]] \
  && note "POSTGRES_PASSWORD 未设置"
[[ "${PLATFORM_CORS_ORIGINS:-*}" == "*" ]] \
  && note "PLATFORM_CORS_ORIGINS 仍是 *，生产必须收紧到白名单域名"
[[ "${PLATFORM_PAYMENT_PROVIDER:-mock}" == "mock" ]] \
  && note "PLATFORM_PAYMENT_PROVIDER 仍是 mock —— 模拟支付上线即事故"
[[ "${PLATFORM_SMS_PROVIDER:-mock}" == "mock" ]] \
  && note "PLATFORM_SMS_PROVIDER 仍是 mock —— 验证码固定 123456，任何人可登录任何账号"
[[ "${PLATFORM_KYC_PROVIDER:-mock}" == "mock" ]] \
  && note "PLATFORM_KYC_PROVIDER 仍是 mock —— 实名形同虚设"
[[ "${PLATFORM_MODERATION_PROVIDER:-local}" == "local" ]] \
  && note "PLATFORM_MODERATION_PROVIDER 仍是 local —— 只有本地词表，看不了图片视频"
[[ "${PLATFORM_LEDGER_BACKEND:-internal}" == "custody" ]] \
  || note "PLATFORM_LEDGER_BACKEND 仍是 internal —— 平台自建账本托管用户资金涉嫌资金池与二清，不得用于真实交易"
[[ -f "${TLS_CERT_DIR:-./certs}/fullchain.pem" ]] \
  || note "缺少 TLS 证书 ${TLS_CERT_DIR:-./certs}/fullchain.pem —— 明文传密码等于没有安全"

if (( fail )); then
  echo
  echo "自检未通过，已中止。这些不是建议，是上线红线。" >&2
  echo "若确认要在预发/演练环境跳过，设 ALLOW_INSECURE=1 重跑。" >&2
  [[ "${ALLOW_INSECURE:-0}" == "1" ]] || exit 1
  echo "⚠️  ALLOW_INSECURE=1，继续启动（切勿用于真实用户）。" >&2
fi

SCALE=1
if [[ "${1:-}" == "--scale" ]]; then SCALE="${2:-1}"; fi

echo "构建并启动（api ×${SCALE}）…"
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d --build --scale "api=${SCALE}"

echo "等待就绪（/readyz）…"
for _ in $(seq 1 60); do
  if docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" \
       exec -T api python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/readyz')" \
       >/dev/null 2>&1; then
    echo "就绪。Web: https://localhost:${WEB_HTTPS_PORT:-443}"
    exit 0
  fi
  sleep 2
done

echo "超时未就绪，查看日志：docker compose -f deploy/$COMPOSE_FILE logs api" >&2
exit 1
