"""EVT-021/022/031 事件投递的运维面：补做、清理、健康、死信。

放在独立模块而不是 main.py：它们是有状态的业务端点（会补做副作用），
和 /healthz 那类无状态探针不是一回事。
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core import events
from app.core.db import get_db
from app.core.deps import require_admin, require_job_auth
from app.core.locks import job_slot
from app.modules.account.models import User

router = APIRouter(prefix="/events", tags=["events"])


@router.post("/jobs/drain")
def drain(db: Session = Depends(get_db), _=Depends(require_job_auth),
          __=Depends(job_slot("event_drain"))):
    """EVT-021 补做失败且可重试的投递。

    受 `job_slot` 单实例锁保护：**任何副本都能补做任何副本发布的事件**，
    这就是 SEC-040 要的跨副本能力——发件箱在库里，不需要额外中间件。
    """
    return events.drain(db)


@router.post("/jobs/purge")
def purge(db: Session = Depends(get_db), _=Depends(require_job_auth),
          __=Depends(job_slot("event_purge"))):
    """EVT-004 清理已完成的旧事件；失败与死信不删。"""
    return events.purge(db)


@router.post("/jobs/purge-security")
def purge_security(db: Session = Depends(get_db), _=Depends(require_job_auth),
                   __=Depends(job_slot("security_purge"))):
    """SECEV-006 清理高频安全事件噪音；封禁与解封的处置留痕不清。"""
    from app.core import guard

    return guard.purge(db)


@router.get("/health")
def health(db: Session = Depends(get_db), _=Depends(require_job_auth)):
    """EVT-031 待重试与死信统计。"""
    return events.health(db)


@router.get("/dead-letters")
def dead_letters(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """EVT-022 待人工处理的投递。

    死信不是「可以忽略的错误列表」——每一条都代表某个用户少了一个本该发生的
    副作用。堆积说明有功能已经悄悄坏了。
    """
    return {"items": events.dead_letters(db),
            "note": "每条死信都代表一个未发生的副作用，需人工判断是否补做"}
