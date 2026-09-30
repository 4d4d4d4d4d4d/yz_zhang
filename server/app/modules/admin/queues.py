"""QUEUE-010 人审队列的**唯一一份声明**（78 号 spec）。

V101 给六个人审队列装了出口，V102 给三个装了入口，而这一批的探针问的是
第三个问题：**东西进来了、出口也有了，谁会去看？**

把四个队列里的东西都推到 30 天前、跑一遍全部 job——管理员和提交方
**一条通知都没有**。而 `SUPPORT_SLA_HOURS = 24` 定义在配置里，
全仓没有任何地方使用它：又一句写下来却没人核对的承诺。

所以队列不能散落在各自的模块里，要有一张表：
**看什么、SLA 多长、超了谁被催、提交方是否被告知（以及为什么不）。**

`tells_submitter` 存的是**理由**而不是布尔值：可疑活动复核那一行不通知
当事人是 AML-030/031 的保密义务，写成 `False` 的话，下一个人会顺手
把它改成 `True`（V90 立下的做法：声明表的值是原因，不是开关）。
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.account.models import utcnow


@dataclass(frozen=True)
class ReviewQueue:
    key: str
    label: str
    # 这个队列的 SLA 从哪个配置项取（名字而不是值：配置改了跟着变）
    sla_setting: str
    # (db) -> [(id, 进入队列的时间, 提交方 user_id 或 None)]
    pending: Callable[[Session], list[tuple[int | str, datetime, int | None]]]
    # 超时告知提交方的理由；空串表示**故意不告知**，见 no_tell_why
    tells_submitter: str
    no_tell_why: str = ""
    # 这个队列的催办是不是由别处负责（例如提现在 75 号里有专门的催办与超时退回）
    chased_elsewhere: str = ""

    def sla_hours(self) -> int:
        return int(getattr(settings, self.sla_setting))


def _tickets(db: Session):
    from app.modules.support.models import Ticket

    return [(t.id, t.created_at, t.user_id)
            for t in db.query(Ticket).filter(Ticket.status == "open").all()]


def _certifications(db: Session):
    from app.modules.account.models_cert import CertificationApplication

    return [(r.id, r.created_at, r.user_id)
            for r in db.query(CertificationApplication)
            .filter(CertificationApplication.status == "pending").all()]


def _teams(db: Session):
    from app.modules.team.models import Team

    # 提交方是 owner：团队本身是个 User 行，但收通知的是人
    return [(t.user_id, t.created_at, t.owner_id)
            for t in db.query(Team).filter(Team.verify_status == "pending").all()]


def _uploads(db: Session):
    from app.modules.files.models import UploadedFile

    return [(r.name, r.created_at, r.owner_id)
            for r in db.query(UploadedFile)
            .filter(UploadedFile.moderation_status == "review").all()]


def _withdrawals(db: Session):
    from app.modules.wallet.models import WithdrawRequest

    return [(r.id, r.created_at, r.user_id)
            for r in db.query(WithdrawRequest)
            .filter(WithdrawRequest.status.in_(("pending", "awaiting_second"))).all()]


def _aml(db: Session):
    from app.modules.aml.models import SuspiciousActivity

    return [(r.id, r.created_at, r.user_id)
            for r in db.query(SuspiciousActivity)
            .filter(SuspiciousActivity.status == "pending").all()]


QUEUES: tuple[ReviewQueue, ...] = (
    ReviewQueue("tickets", "客服工单", "SUPPORT_SLA_HOURS", _tickets,
                tells_submitter="提问的人等的是一个答复；沉默让他以为自己被忽略了"),
    ReviewQueue("certifications", "受限类目资质", "REVIEW_SLA_HOURS", _certifications,
                tells_submitter="资质没核过就接不了受限类目的单，他在等一个能不能干活的答复"),
    ReviewQueue("teams", "团队企业信息", "REVIEW_SLA_HOURS", _teams,
                tells_submitter="核过才能开票，财务在等这张票"),
    ReviewQueue("uploads", "图片人审", "REVIEW_SLA_HOURS", _uploads,
                tells_submitter="图片卡在人审里，用他做交付凭证的那一单也跟着卡住"),
    ReviewQueue("withdrawals", "提现人审", "WITHDRAW_REVIEW_REMIND_HOURS", _withdrawals,
                tells_submitter="钱冻着，这是最该说话的一类",
                chased_elsewhere="75 号已有专门的催办与超时退回；"
                                 "再加一套等于每小时两条通知，运营会把整类关掉"),
    ReviewQueue("aml", "可疑活动复核", "REVIEW_SLA_HOURS", _aml,
                tells_submitter="",
                no_tell_why="AML-030/031：《反洗钱法》的保密义务不允许告诉当事人"
                            "「你被标记了、正在复核」——说了等于教他下次怎么规避"),
)

BY_KEY = {q.key: q for q in QUEUES}


def snapshot(db: Session, now: datetime | None = None) -> list[dict]:
    """每个队列：几件在等、最久等了多久、SLA 多长、超没超。

    三个地方共用这一份：催办 job、管理后台首屏、测试。
    各自去数库就会出现三份不一样的答案。
    """
    now = now or utcnow()
    out = []
    for q in QUEUES:
        rows = q.pending(db)
        oldest = min((at for _id, at, _uid in rows), default=None)
        waited = int((now - oldest).total_seconds() // 3600) if oldest else 0
        sla = q.sla_hours()
        out.append({
            "key": q.key,
            "label": q.label,
            "pending": len(rows),
            "oldest_wait_hours": waited,
            "sla_hours": sla,
            "breached": bool(rows) and waited >= sla,
            # 运营要能看出「这个队列有没有人盯」——答案可能是「有，在别处」
            "chased_elsewhere": q.chased_elsewhere,
        })
    return out
