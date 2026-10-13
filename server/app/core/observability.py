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

# DEP-040 / SEC-065 敏感串脱敏。
#
# 只认三种数字（手机号 / 证件号 / 卡号）的那一版漏掉了凭据：本平台的登录 token、
# `Authorization: Bearer …`、表单里的 `password=` / `sms_code=`、邮箱，
# 以及 SQLAlchemy 异常里原样带着的 `[parameters: (...)]`（注册撞唯一约束时那里面就是手机号与密码哈希）。
_SECRET_KEYS = r"password|passwd|pwd|new_password|old_password|token|access_token|refresh_token|secret|" \
               r"api_key|apikey|sms_code|verify_code|captcha|id_number|authorization|signature"
_PATTERNS = [
    # SQL 绑定参数整块去掉：引擎已设 hide_parameters，这一条是第二道
    (re.compile(r"\[parameters: .*?\](?=\s|$)", re.S), "[parameters: redacted]"),
    # 本平台的 token（base64 载荷 . 64 位 HMAC）与任何 Bearer 凭据
    (re.compile(r"[A-Za-z0-9_\-]{16,}={0,2}\.[0-9a-f]{64}"), "[token]"),
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=\-]+"), "Bearer [redacted]"),
    # key=value / "key": "value" / 'key': 'value' 形式的凭据
    (re.compile(rf"(?i)(\b(?:{_SECRET_KEYS})\b\s*[=:]\s*)([\"']?)[^\s,&;\"'}}]+\2"), r"\1\2[redacted]\2"),
    (re.compile(rf"(?i)([\"'](?:{_SECRET_KEYS})[\"']\s*:\s*)([\"'])[^\"']*\2"), r"\1\2[redacted]\2"),
    # 邮箱：留首字母与域名，够排障用，不够认人
    (re.compile(r"\b([A-Za-z0-9])[A-Za-z0-9._%+\-]*@([A-Za-z0-9.\-]+\.[A-Za-z]{2,})\b"), r"\1***@\2"),
    (re.compile(r"(?<!\d)(1[3-9]\d)\d{4}(\d{4})(?!\d)"), r"\1****\2"),      # 手机号
    (re.compile(r"(?<!\d)(\d{6})\d{8}(\d{3}[\dXx])(?!\d)"), r"\1********\2"),  # 身份证
    (re.compile(r"(?<!\d)(\d{4})\d{8,11}(\d{4})(?!\d)"), r"\1********\2"),  # 银行卡
]


def redact(text: str) -> str:
    for pattern, repl in _PATTERNS:
        text = pattern.sub(repl, text)
    return text


_EXTRA_KEYS = ("path", "method", "status", "duration_ms", "user_id")


class JsonFormatter(logging.Formatter):
    """一行一个 JSON，全部字段过脱敏。

    SEC-065：异常堆栈此前被**整个丢掉**（格式化器只输出 message）——生产出 500 时
    日志里只有一句「request」，查不了；而直接补回堆栈又会把异常文本里的个人信息带出来。
    所以堆栈补回来，并且和 message 走同一道脱敏。脱敏本身出错时**丢内容、不丢脱敏**。
    """

    def format(self, record: logging.LogRecord) -> str:
        try:
            payload = {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)),
                "level": record.levelname,
                "logger": record.name,
                "msg": redact(record.getMessage()),
                "request_id": request_id_var.get(""),
            }
            for key in _EXTRA_KEYS:
                if hasattr(record, key):
                    v = getattr(record, key)
                    payload[key] = redact(v) if isinstance(v, str) else v
            if record.exc_info:
                payload["exc"] = redact(self.formatException(record.exc_info))
            return json.dumps(payload, ensure_ascii=False)
        except Exception:  # noqa: BLE001 - 脱敏失败时宁可丢这一条的内容
            return json.dumps({"level": getattr(record, "levelname", "ERROR"),
                               "logger": getattr(record, "name", ""),
                               "msg": "[log redaction failed; content dropped]"})


class _DropServerDuplicate(logging.Filter):
    """uvicorn 对同一个未处理异常再记一遍（不带 request_id）；中间件已经记过，这条去掉。"""

    def filter(self, record: logging.LogRecord) -> bool:
        return not record.getMessage().startswith("Exception in ASGI application")


def setup_logging(level: str = "INFO") -> None:
    """全进程只有一个出口：stdout 上的 JSON 行，经过脱敏。

    SEC-065：uvicorn 自带一套日志配置，它的两类日志此前**绕开了这里**——
    - `uvicorn.error`（启动信息与**未处理异常的堆栈**）：纯文本、不脱敏；
      一次撞唯一约束的 500 会把 SQL 参数（手机号、密码哈希）原样打到 stderr；
    - `uvicorn.access`：带**查询串**与客户端 IP，`/search?q=…` 的原始搜索词每条都进日志——
      而 V127 刚定下搜索词是个人信息（不存身份、k-匿名）。
    前者改为汇入这里；后者关掉（访问日志由 ObservabilityMiddleware 记，只记路由模板、不记查询串）。
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    for name in ("uvicorn", "uvicorn.error"):
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.propagate = True
    err = logging.getLogger("uvicorn.error")
    if not any(isinstance(f, _DropServerDuplicate) for f in err.filters):
        err.addFilter(_DropServerDuplicate())
    access = logging.getLogger("uvicorn.access")
    access.handlers = []
    access.propagate = False
    access.disabled = True


# ── DEP-042 指标：进程内计数（多副本由 Prometheus 按实例聚合）──────────
_req_total: dict[tuple[str, int], int] = defaultdict(int)
_req_duration_sum: dict[str, float] = defaultdict(float)
_req_duration_count: dict[str, int] = defaultdict(int)
# 延迟分桶（秒），Prometheus histogram 语义
_BUCKETS = (0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0)
_req_buckets: dict[float, int] = defaultdict(int)


UNMATCHED = "<unmatched>"


def _route_of(request) -> str:
    """用路由模板而非真实路径，避免 /tasks/123 把指标基数打爆。

    SEC-065：没匹配上任何路由的请求（404、扫描器）此前回落到**原始路径**——
    任何人随便请求 `/api/v1/<随机串>` 就能让指标的标签数无限增长（进程内存跟着涨），
    原始路径还会把人家塞进 URL 的东西原样写进日志。没匹配上的统一记成一个标签。
    """
    route = request.scope.get("route")
    return getattr(route, "path", None) or UNMATCHED


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
        except Exception:
            # 未处理异常在这里记一次：带 request_id、过脱敏、**带堆栈**。
            # uvicorn 随后那条不带 request_id 的重复记录由 _DropServerDuplicate 去掉
            logging.getLogger("app.error").exception(
                "unhandled exception", extra={"path": _route_of(request), "method": request.method})
            raise
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

    # CONC-067 生产上「调供应商时还挂着事务」不打挂请求，只在这里被看见
    from app.core import txguard

    lines += ["# HELP vendor_call_in_transaction_total 调供应商时还挂着数据库事务的次数（应为 0）",
              "# TYPE vendor_call_in_transaction_total counter"]
    for call, count in sorted(txguard.violations.items()):
        lines.append(f'vendor_call_in_transaction_total{{call="{_escape(call)}"}} {count}')

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

    # AGT-054 LLM 降级次数。降级本身是对的（宁可给模板结果也不要让发布卡住），
    # 但**它必须看得见**：一个过期的型号字面量曾经可以让每次调用都 404，
    # 而平台看起来完全正常。
    from app.modules.decompose.llm import fallback_counts

    counts = fallback_counts()
    lines += ["# HELP llm_decompose_fallback_total 分解降级到模板引擎的次数",
              "# TYPE llm_decompose_fallback_total counter"]
    if counts:
        for kind, n in sorted(counts.items()):
            lines.append(f'llm_decompose_fallback_total{{error_type="{_escape(kind)}"}} {n}')
    else:
        lines.append('llm_decompose_fallback_total{error_type="none"} 0')

    # AI-DEC-045 逐层拆解每条保险的触发次数（106 号 spec）。全部原因都出一行，
    # 0 也出——看板上「没有这条线」和「这条线是 0」是两回事
    from app.modules.decompose.tree import stop_counts

    lines += ["# HELP decompose_stop_total 逐层拆解在某条保险上停下的次数",
              "# TYPE decompose_stop_total counter"]
    for reason, n in sorted(stop_counts().items()):
        lines.append(f'decompose_stop_total{{reason="{reason}"}} {n}')

    # KB-071 归并被拒的次数（没标定阈值 / 阈值是旧模型标的）。宁可不归并、
    # 不要用错的阈值归并——但被拒必须看得见，否则经验就静静地堆在待定区里
    from app.modules.knowledge.clusters import held_counts

    lines += ["# HELP knowledge_cluster_held_total 经验归并因阈值缺失或模型不符被拒的次数",
              "# TYPE knowledge_cluster_held_total counter"]
    for reason, n in sorted(held_counts().items()):
        lines.append(f'knowledge_cluster_held_total{{reason="{reason}"}} {n}')

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
        # DRILL-041 以下三个是**为告警规则补的**。写 deploy/alerts.prom.yml 时
        # 才发现最重要的三条（资金不平、job 静默、审核积压）引用的指标
        # 根本不存在——引用不存在指标的告警永远不会触发，而且是静默的。
        # 一个「配了却从不告警」的监控比没有监控更危险：你以为自己被盖住了。
        "# HELP platform_reconcile_ok 五条资金不变量是否全部成立（1/0）",
        "# TYPE platform_reconcile_ok gauge",
        f"platform_reconcile_ok {1 if _reconcile_ok(db) else 0}",
        "# HELP platform_jobs_unhealthy 从未跑过或已陈旧的 job 数（never_run + stale）",
        "# TYPE platform_jobs_unhealthy gauge",
        f"platform_jobs_unhealthy {never_run + stale}",
        "# HELP platform_uploads_pending_review 待人工复核的上传图片数",
        "# TYPE platform_uploads_pending_review gauge",
        f"platform_uploads_pending_review {_pending_uploads(db)}",
    ]


def _reconcile_ok(db) -> bool:
    """对账是只读聚合，指标端点自己就能算——不必等日终 job。

    日终 job 会开差错工单，那是 T+1；这个指标是实时的那一半。
    """
    from app.modules.risk import service as risk

    try:
        return bool(risk.reconcile(db).get("ok"))
    except Exception:
        # 指标端点不能因为一个聚合出错就整体 500——那会让**所有**告警一起瞎掉
        return False


def _pending_uploads(db) -> int:
    from app.modules.files.models import UploadedFile

    try:
        return int(
            db.query(func.count(UploadedFile.name))
            .filter(UploadedFile.moderation_status == "review").scalar() or 0
        )
    except Exception:
        return 0


def reset_metrics() -> None:
    """测试辅助。"""
    _req_total.clear()
    _req_duration_sum.clear()
    _req_duration_count.clear()
    _req_buckets.clear()
