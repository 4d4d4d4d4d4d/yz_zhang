"""VND-002~005 供应商接入公共设施：错误收敛、调用留痕、幂等、熔断。

设计原则：**业务模块只依赖本包的接口，永远不 import 任何供应商 SDK**。
换供应商 = 加一个实现类 + 改一个环境变量，业务代码零改动。
"""
import time
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import bad_request


class VendorError(Exception):
    """VND-002 供应商失败统一收敛。

    `retryable=True` 表示网络/限流类可重试故障（→ 502），
    `False` 表示供应商明确拒绝（→ 400），业务侧据此决定提示文案。
    **原始报文不进入 message**，避免把供应商内部信息泄露给终端用户。
    """

    def __init__(self, code: str, message: str, retryable: bool = True):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable

    def as_http(self):
        from fastapi import HTTPException

        status = 502 if self.retryable else 400
        return HTTPException(
            status_code=status,
            detail={"code": f"vendor_{self.code}", "message": self.message},
        )


@dataclass
class VendorResult:
    """统一返回体：`ok` + 供应商外部单号 + 归一化后的数据。"""

    ok: bool
    external_ref: str = ""
    status: str = "succeeded"
    data: dict[str, Any] = field(default_factory=dict)


# ── VND-005 熔断：同一 provider 连续失败进入冷却，冷却期直接快速失败 ──
_failures: dict[str, int] = {}
_open_until: dict[str, float] = {}

FAIL_THRESHOLD = 5
COOLDOWN_SECONDS = 30


def circuit_check(name: str) -> None:
    if time.time() < _open_until.get(name, 0):
        raise VendorError("circuit_open", "外部服务暂时不可用，请稍后重试", retryable=True)


def circuit_record(name: str, ok: bool) -> None:
    if ok:
        _failures[name] = 0
        _open_until.pop(name, None)
        return
    _failures[name] = _failures.get(name, 0) + 1
    if _failures[name] >= FAIL_THRESHOLD:
        _open_until[name] = time.time() + COOLDOWN_SECONDS


def circuit_reset() -> None:
    """测试辅助。"""
    _failures.clear()
    _open_until.clear()


def circuit_state(name: str) -> str:
    if time.time() < _open_until.get(name, 0):
        return "open"
    return "closed" if _failures.get(name, 0) == 0 else "half-open"


# ── VND-003/004 调用留痕 + 幂等 ────────────────────────────────────
def _digest(params: dict) -> str:
    """请求摘要（脱敏）：只留字段名与长度/金额，不落敏感明文。"""
    safe = {}
    for k, v in params.items():
        if k in ("id_no", "id_number", "code", "account_no", "phone"):
            safe[k] = f"<{len(str(v))} chars>"
        else:
            safe[k] = v
    return str(safe)[:400]


def call(db: Session, kind: str, provider: str, operation: str, params: dict, fn,
         idem_key: str = "") -> VendorResult:
    """统一执行入口：幂等 → 熔断 → 调用 → 留痕 → 错误收敛。

    幂等（VND-004）针对「会花钱/会发送」的操作：同一 `idem_key` 已成功过，
    直接回放首次结果，绝不二次打供应商。
    """
    from .models import VendorCall

    name = f"{kind}:{provider}"
    if idem_key:
        prior = (
            db.query(VendorCall)
            .filter(VendorCall.idem_key == idem_key, VendorCall.status == "succeeded")
            .first()
        )
        if prior:
            return VendorResult(ok=True, external_ref=prior.external_ref, status="succeeded",
                                data={"replayed": True})

    circuit_check(name)
    started = time.time()
    record = VendorCall(
        kind=kind, provider=provider, operation=operation,
        idem_key=idem_key or None, request_digest=_digest(params),
    )
    try:
        result: VendorResult = fn()
    except VendorError as exc:
        circuit_record(name, ok=False)
        record.status = "failed"
        record.error_code = exc.code
        record.duration_ms = int((time.time() - started) * 1000)
        db.add(record)
        db.flush()
        raise
    except Exception as exc:  # 供应商 SDK 的意外异常也收敛，不让原始栈冒到 API
        circuit_record(name, ok=False)
        record.status = "failed"
        record.error_code = type(exc).__name__
        record.duration_ms = int((time.time() - started) * 1000)
        db.add(record)
        db.flush()
        raise VendorError("unavailable", "外部服务调用失败", retryable=True) from exc

    circuit_record(name, ok=result.ok)
    record.status = result.status if result.ok else "failed"
    record.external_ref = result.external_ref
    record.duration_ms = int((time.time() - started) * 1000)
    db.add(record)
    db.flush()
    return result


def require_amount(amount_cents: int) -> None:
    if amount_cents <= 0:
        raise bad_request("金额必须为正", "invalid_amount")


def masked(value: str) -> str:
    """VND-040 密钥/账号掩码：健康检查与后台展示用，永不回显明文。"""
    if not value:
        return ""
    if len(value) <= 8:
        return "****"
    return f"{value[:4]}****{value[-4:]}"


def is_prod() -> bool:
    return settings.ENV == "prod"
