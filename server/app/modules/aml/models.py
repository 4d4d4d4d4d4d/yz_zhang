"""AML-020 可疑活动记录（30 号 spec）。

**只增不改**：可疑判断连同当时的触发依据一起冻结下来。
事后把「为什么当时觉得可疑」改掉，等于销毁了自己的合规底稿。
"""
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.modules.account.models import utcnow

# 形态代码 → 中文说明（管理端展示用；**不得**出现在任何面向用户的出口，见 AML-030）
PATTERNS = {
    "structuring": "拆分规避阈值：短时间内多笔金额接近但均低于单笔人审门槛",
    "passthrough": "快进快出：充值后短时间内几乎原样提现，中间无真实成交",
    "paired_trading": "高频对敲：同一对用户反复互相成交",
    "account_clustering": "收款账户聚集：多个用户绑定同一收款账户",
    "large_amount": "大额交易：单笔或当日累计达到大额报告线",
    "sanctions_hit": "名单命中：主体命中制裁/涉恐名单",
}

STATUSES = ("pending", "cleared", "to_report", "reported")


class SuspiciousActivity(Base):
    __tablename__ = "suspicious_activities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    pattern: Mapped[str] = mapped_column(String(32), index=True)
    # 触发依据要带**具体数值**：只写「疑似拆分」，复核的人无从判断
    detail: Mapped[str] = mapped_column(Text, default="")
    amount_cents: Mapped[int] = mapped_column(Integer, default=0)
    # 关联对象（withdraw_request / task / payout_account…），便于复核时回溯
    ref_type: Mapped[str] = mapped_column(String(24), default="")
    ref_id: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(12), default="pending", index=True)
    reviewer_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    review_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
