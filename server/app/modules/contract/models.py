from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.modules.account.models import utcnow

# SC 合约生命周期：pending_signatures → signed → funded → released/refunded/split/cancelled
CONTRACT_STATUSES = [
    "pending_signatures",
    "signed",
    "funded",
    "released",
    "refunded",
    "split",
    "cancelled",
]

# ACCDEL-012 资金已彻底出账的终态。账号注销闸门按「**不在**这张表里就算进行中」
# 判断，而不是手抄一张「进行中」的白名单——那种白名单抄漏了不会有任何东西报错。
# 以后新增一个状态，忘了登记的方向是「多拦一次注销」，不是「放走一笔钱」。
SETTLED_STATUSES: frozenset[str] = frozenset({"released", "refunded", "split", "cancelled"})


class Contract(Base):
    __tablename__ = "contracts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    requester_id: Mapped[int] = mapped_column(Integer, index=True)
    executor_id: Mapped[int] = mapped_column(Integer, index=True)
    amount_cents: Mapped[int] = mapped_column(Integer)
    released_cents: Mapped[int] = mapped_column(Integer, default=0)  # SC-004 已分期放款累计
    fee_bps: Mapped[int] = mapped_column(Integer)  # SC-009 平台佣金（万分比）
    terms: Mapped[str] = mapped_column(Text, default="")  # SC-001 条款文本（由任务要素生成）
    status: Mapped[str] = mapped_column(String(30), default="pending_signatures")
    signed_by_requester: Mapped[bool] = mapped_column(Boolean, default=False)
    signed_by_executor: Mapped[bool] = mapped_column(Boolean, default=False)
    frozen: Mapped[bool] = mapped_column(Boolean, default=False)  # SC-008 纠纷冻结
    version: Mapped[int] = mapped_column(Integer, default=1)  # SC-007 变更单生效则 +1
    # CONC-013 乐观锁：与业务版本号 version 分离（后者是合约条款版本，会被展示与导出）。
    # 每次 ORM UPDATE 自动 +1 并进入 WHERE 条件，并发写第二个提交拿到 StaleDataError → 409
    lock_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # CRED-005 执行者保证金
    # OUT-003 浮动对价部分。**与基础报酬一并托管**——不托管的话
    # 「做得好多给钱」就只是一句口头承诺，执行方干到了水平也没东西可执行。
    bonus_cents: Mapped[int] = mapped_column(Integer, default=0)
    deposit_cents: Mapped[int] = mapped_column(Integer, default=0)
    deposit_status: Mapped[str] = mapped_column(String(12), default="none")  # none/held/returned/forfeited
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    funded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __mapper_args__ = {"version_id_col": lock_version}


class Milestone(Base):
    """SC-004 里程碑分期：每期独立交付/验收/放款。默认单期=全额。"""

    __tablename__ = "milestones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    contract_id: Mapped[int] = mapped_column(Integer, index=True)
    idx: Mapped[int] = mapped_column(Integer)  # 1..n
    title: Mapped[str] = mapped_column(String(120), default="")
    amount_cents: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/delivered/released
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    # SC-015（296 号 spec）一次交付多期时写的交付说明（几期共用一份）；逐期交付不写，照旧为空
    delivery_note: Mapped[str] = mapped_column(String(500), default="")


class ChangeOrder(Base):
    """SC-007 变更单：改价需对方接受，生效后合约版本 +1、托管差额多退少补。"""

    __tablename__ = "change_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    contract_id: Mapped[int] = mapped_column(Integer, index=True)
    proposed_by: Mapped[int] = mapped_column(Integer)
    new_amount_cents: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(500), default="")
    # SC-007b 真实的「加了两个房间」通常同时要改期、改范围。不改价时 new_amount_cents 记原金额
    new_deadline: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    scope_change: Mapped[str] = mapped_column(String(1000), default="")
    # SCN-139（207 号 spec）多天名额改时段：对方接受后名额的时段跟着改。None = 这张变更单不改时段，"" = 改成不限时段
    new_shift_start: Mapped[str | None] = mapped_column(String(5), nullable=True)
    new_shift_end: Mapped[str | None] = mapped_column(String(5), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/accepted/rejected
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ContractSignature(Base):
    """LAW-002 签署留痕：谁、何时、对**哪一份文本**表示同意。

    `document_hash` 是签署那一刻的合同全文哈希——事后改条款则对不上，
    篡改自证。`reliability` 诚实标注证明力：
      platform_witness  平台见证（能证明文本未改，**不能独立证明签名人身份**）
      qualified         第三方 CA 签发证书 + 可信时间戳（《电子签名法》可靠电子签名）
    """

    __tablename__ = "contract_signatures"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    contract_id: Mapped[int] = mapped_column(Integer, index=True)
    signer_id: Mapped[int] = mapped_column(Integer, index=True)
    role: Mapped[str] = mapped_column(String(12))          # requester / executor
    # 合同版本：变更单生效后是新版本，各版本独立签署与独立存证
    contract_version: Mapped[int] = mapped_column(Integer, default=1)
    document_hash: Mapped[str] = mapped_column(String(64), index=True)
    signature: Mapped[str] = mapped_column(String(512), default="")
    certificate: Mapped[str] = mapped_column(Text, default="")
    timestamp_token: Mapped[str] = mapped_column(Text, default="")
    algorithm: Mapped[str] = mapped_column(String(32), default="")
    reliability: Mapped[str] = mapped_column(String(24), default="platform_witness")
    provider: Mapped[str] = mapped_column(String(32), default="platform")
    extra: Mapped[dict] = mapped_column(JSON, default=dict)
    signed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ContractDeliverable(Base):
    """SCN-166（297 号 spec）交付文件托管在平台：执行方传预览图（自己加水印或缩小）与原图；
    原图在合约放款完毕前只有执行方能取，发布方验收放款后才能下载——「先交片后不付」与「付了不交片」两头都堵上。"""

    __tablename__ = "contract_deliverables"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    contract_id: Mapped[int] = mapped_column(Integer, index=True)
    file_name: Mapped[str] = mapped_column(String(80))       # uploaded_files.name
    kind: Mapped[str] = mapped_column(String(10))            # preview / original
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    # SC-017（304 号 spec）挂到哪一期（idx）；None = 整份合约（V324 的行为：放款完毕才解锁）。
    # 挂到某一期的原图，那一期放款后就解锁，不用等整份合约放完
    milestone_idx: Mapped[int | None] = mapped_column(Integer, nullable=True)
