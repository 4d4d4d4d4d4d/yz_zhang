"""DEP-040~042 可观测：结构化日志、request_id、Prometheus 指标。

日志脱敏是硬性要求：手机号、证件号、验证码、token、银行卡**永远不进日志**。
出事时能查是次要的，出事时不能因为日志本身再泄一次才是底线。
"""
import json
import logging
import re
import sys
import time
import uuid
from collections import defaultdict
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware

request_id_var: ContextVar[str] = ContextVar("request_id", default="")

# DEP-040 敏感串脱敏：手机号 / 18 位证件号 / 长数字（卡号）
_PATTERNS = [
    (re.compile(r"(?<!\d)(1[3-9]\d)\d{4}(\d{4})(?!\d)"), r"\1****\2"),      # 手机号
    (re.compile(r"(?<!\d)(\d{6})\d{8}(\d{3}[\dXx])(?!\d)"), r"\1********\2"),  # 身份证
    (re.compile(r"(?<!\d)(\d{4})\d{8,11}(\d{4})(?!\d)"), r"\1********\2"),  # 银行卡
]


def redact(text: str) -> str:
    for pattern, repl in _PATTERNS:
        text = pattern.sub(repl, text)
    return text


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "msg": redact(record.getMessage()),
            "request_id": request_id_var.get(""),
        }
        for key in ("path", "method", "status", "duration_ms", "user_id"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)


# ── DEP-042 指标：进程内计数（多副本由 Prometheus 按实例聚合）──────────
_req_total: dict[tuple[str, int], int] = defaultdict(int)
_req_duration_sum: dict[str, float] = defaultdict(float)
_req_duration_count: dict[str, int] = defaultdict(int)
# 延迟分桶（秒），Prometheus histogram 语义
_BUCKETS = (0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0)
_req_buckets: dict[float, int] = defaultdict(int)


def _route_of(request) -> str:
    """用路由模板而非真实路径，避免 /tasks/123 把指标基数打爆。"""
    route = request.scope.get("route")
    return getattr(route, "path", request.url.path)


class ObservabilityMiddleware(BaseHTTPMiddleware):
    """DEP-041 request_id 贯穿：入站生成或透传，随响应头返回。"""

    async def dispatch(self, request, call_next):
        rid = request.headers.get("X-Request-Id") or uuid.uuid4().hex[:16]
        token = request_id_var.set(rid)
        started = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["X-Request-Id"] = rid
            return response
        finally:
            elapsed = time.perf_counter() - started
            route = _route_of(request)
            _req_total[(route, status)] += 1
            _req_duration_sum[route] += elapsed
            _req_duration_count[route] += 1
            for b in _BUCKETS:
                if elapsed <= b:
                    _req_buckets[b] += 1
            logging.getLogger("access").info(
                "request",
                extra={"path": route, "method": request.method,
                       "status": status, "duration_ms": round(elapsed * 1000, 2)},
            )
            request_id_var.reset(token)


def _escape(v: str) -> str:
    return v.replace("\\", "\\\\").replace('"', '\\"')


def render_metrics(db=None) -> str:
    """Prometheus 文本格式。除请求指标外，附**资金关键计数**——
    托管中金额、待提现、纠纷未决数是这门生意的心跳，比 CPU 重要。"""
    lines = [
        "# HELP http_requests_total HTTP 请求总数",
        "# TYPE http_requests_total counter",
    ]
    for (route, status), count in sorted(_req_total.items()):
        lines.append(f'http_requests_total{{route="{_escape(route)}",status="{status}"}} {count}')

    lines += ["# HELP http_request_duration_seconds 请求耗时", "# TYPE http_request_duration_seconds histogram"]
    total_count = sum(_req_duration_count.values())
    total_sum = sum(_req_duration_sum.values())
    cumulative = 0
    for b in _BUCKETS:
        cumulative = max(cumulative, _req_buckets[b])
        lines.append(f'http_request_duration_seconds_bucket{{le="{b}"}} {cumulative}')
    lines.append(f'http_request_duration_seconds_bucket{{le="+Inf"}} {total_count}')
    lines.append(f"http_request_duration_seconds_sum {total_sum:.6f}")
    lines.append(f"http_request_duration_seconds_count {total_count}")

    if db is not None:
        lines += _business_metrics(db)
    return "\n".join(lines) + "\n"


def _business_metrics(db) -> list[str]:
    from sqlalchemy import func

    from app.modules.dispute.models import Dispute
    from app.modules.wallet.models import WalletAccount, WithdrawRequest

    escrow = db.query(func.coalesce(func.sum(WalletAccount.escrow_cents), 0)).scalar() or 0
    frozen = db.query(func.coalesce(func.sum(WalletAccount.frozen_cents), 0)).scalar() or 0
    pending_withdraw = (
        db.query(func.coalesce(func.sum(WithdrawRequest.amount_cents), 0))
        .filter(WithdrawRequest.status == "pending").scalar() or 0
    )
    open_disputes = (
        db.query(func.count(Dispute.id))
        .filter(Dispute.status.notin_(("resolved", "closed", "settled"))).scalar() or 0
    )
    from app.core import events
    from app.core.locks import job_health

    evt = events.health(db)
    jobs = job_health(db)
    never_run = sum(1 for j in jobs if j.get("never_run"))
    stale = sum(1 for j in jobs if j.get("stale"))
    return [
        "# HELP platform_escrow_cents 托管中资金（分）",
        "# TYPE platform_escrow_cents gauge",
        f"platform_escrow_cents {int(escrow)}",
        "# HELP platform_frozen_cents 冻结中资金（分）",
        "# TYPE platform_frozen_cents gauge",
        f"platform_frozen_cents {int(frozen)}",
        "# HELP platform_pending_withdraw_cents 待审提现（分）",
        "# TYPE platform_pending_withdraw_cents gauge",
        f"platform_pending_withdraw_cents {int(pending_withdraw)}",
        "# HELP platform_open_disputes 未结纠纷数",
        "# TYPE platform_open_disputes gauge",
        f"platform_open_disputes {int(open_disputes)}",
        # EVT-030 死信堆积是「有功能已经悄悄坏了」的最早信号：
        # 用户少收了通知、经验没入库，业务面上一切正常，只有这个数会涨
        "# HELP platform_event_pending_retry 待补做的事件投递数",
        "# TYPE platform_event_pending_retry gauge",
        f"platform_event_pending_retry {int(evt['pending_retry'])}",
        "# HELP platform_event_dead_letters 需人工处理的事件投递数",
        "# TYPE platform_event_dead_letters gauge",
        f"platform_event_dead_letters {int(evt['dead_letters'])}",
        # JOB-011 「从未跑过」必须能被告警看见。此前监控只罗列已有记录，
        # 一个从没被调度过的 job（比如资金对账）在指标里根本不存在
        "# HELP platform_jobs_never_run 应有但从未成功执行过的 job 数",
        "# TYPE platform_jobs_never_run gauge",
        f"platform_jobs_never_run {never_run}",
        "# HELP platform_jobs_stale 超过自身周期 3 倍未成功的 job 数",
        "# TYPE platform_jobs_stale gauge",
        f"platform_jobs_stale {stale}",
    ]


def reset_metrics() -> None:
    """测试辅助。"""
    _req_total.clear()
    _req_duration_sum.clear()
    _req_duration_count.clear()
    _req_buckets.clear()
