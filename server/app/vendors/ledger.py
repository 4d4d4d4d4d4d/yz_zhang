"""FIN-050/051/052 资金事实来源抽象。

> **上线红线**：`InternalLedger` 让用户资金沉淀在平台自己控制的账户里，
> 平台再自行拆分转付——这在国内构成**资金池 + 二清**（无证从事支付结算）。
> 账本写得再严谨、不变量校验得再全，都不改变这个定性：
> **问题不在代码质量，在资金的法律路径。**
>
> 因此 `startup_check` 在 `PLATFORM_ENV=prod` 且后端为 internal 时**拒绝启动**。
> 这不是保守，是把「不能这样上线」变成一道机器执行的闸门。

合规形态（`CustodyLedger`）：
    付款方 → 持牌机构的存管账户（平台无支配权）
                 └── 平台只发分账指令 → 存管方执行 → 收款方
"""
from typing import Protocol

from sqlalchemy.orm import Session

from app.core.config import settings


class LedgerBackend(Protocol):
    name: str
    is_custody: bool

    def execute(self, db: Session, order, splits: list) -> str:
        """执行分账指令，返回外部流水号（内部账本返回空串）。"""


class InternalLedger:
    """平台内账本。**仅限开发与演示**，不得用于真实资金。

    这里不做资金搬运——搬运已由 `wallet` 模块的既有原语完成，
    本后端只确认「指令已按内部账本执行」，指令本身作为对账镜像留存（FIN-002）。
    """

    name = "internal"
    is_custody = False

    def execute(self, db: Session, order, splits: list) -> str:
        return ""


class CustodyLedger:
    """持牌机构存管。把分账指令下达给存管方，钱不经过平台。

    接口按通用担保交易/分账产品的形态预留；具体实现需要与存管方签约后
    按其 SDK 填充 `split_settle`（FIN-003）。
    """

    name = "custody"
    is_custody = True

    def execute(self, db: Session, order, splits: list) -> str:
        from .base import VendorError
        from .registry import get_provider

        provider = get_provider("payment")
        split_fn = getattr(provider, "split_settle", None)
        if split_fn is None:
            raise VendorError(
                "custody_unsupported",
                "当前支付供应商未实现分账指令（split_settle），无法以存管方式结算",
                retryable=False,
            )
        result = split_fn(
            order_no=f"ST{order.id}",
            splits=[{"payee": s.payee_user_id, "amount_cents": s.amount_cents,
                     "purpose": s.purpose} for s in splits],
        )
        return result.external_ref


_REGISTRY = {"internal": InternalLedger, "custody": CustodyLedger}
_backend: LedgerBackend | None = None


def get_ledger() -> LedgerBackend:
    global _backend
    if _backend is None:
        factory = _REGISTRY.get(settings.LEDGER_BACKEND, InternalLedger)
        _backend = factory()
    return _backend


def reset() -> None:
    """测试辅助：切换配置后清缓存。"""
    global _backend
    _backend = None


def is_sandbox() -> bool:
    """FIN-053 未接存管 = 沙箱：API 响应显式标注，避免有人误以为这是真实资金。"""
    return not get_ledger().is_custody
