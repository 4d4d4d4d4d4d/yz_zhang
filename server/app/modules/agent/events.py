"""AGT-019 agent 收入归集到平台账户。

**不为 agent 另开一条放款路径。** 放款照常走 `escrow_release` 进 agent 的钱包，
然后在这里用既有的 `transfer()` 归集到平台账户。理由是五条资金不变量——
另写一条放款路径是这一批最容易把它们打破的地方，而打破之后
日终对账会报「全局守恒不符」，排查成本远高于多一次转账。
"""
from sqlalchemy.orm import Session

from app.core.events import subscribe
from app.modules.account.models import User
from app.modules.wallet import service as wallet


def _on_task_completed(db: Session, payload: dict) -> None:
    from app.modules.task.models import Task

    task = db.get(Task, payload["task_id"])
    if not task or not task.executor_id:
        return
    executor = db.get(User, task.executor_id)
    if not executor or not executor.is_agent:
        return
    acct = wallet.get_or_create(db, executor.id)
    amount = acct.available_cents
    if amount <= 0:
        return
    # agent 是平台自有的，它钱包里的余额就是平台的钱——留在那儿只会让
    # 「平台账户余额」这个经营数字失真
    wallet.transfer(
        db, executor.id, wallet.PLATFORM_USER_ID, amount,
        contract_id=None, memo=f"AI 助理「{executor.nickname}」任务收入归集",
        kind="agent_payout",
    )


def register_event_handlers() -> None:
    # 可重试：归集是幂等的——按「当前可用余额」转账，补做一次只会转 0 元。
    subscribe("task.completed", _on_task_completed, retry=True)
