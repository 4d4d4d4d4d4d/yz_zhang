"""AML-022/030 可疑活动的管理端出口。

**整个路由只对管理员开放，没有任何面向用户的端点**——这是刻意的：
《反洗钱法》第五条要求对反洗钱工作信息保密，可疑标记一旦出现在
用户能看到的任何地方（包括数据导出），就构成泄露（tipping-off）。
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_admin
from app.modules.account.models import User

from . import service

router = APIRouter(prefix="/admin/aml", tags=["aml"])


@router.get("/activities")
def activities(status: str = "pending", admin: User = Depends(require_admin),
               db: Session = Depends(get_db)):
    return service.listing(db, status)


@router.get("/stats")
def stats(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.stats(db)


class ReviewIn(BaseModel):
    # cleared = 复核无问题；to_report = 待报送；reported = 已报送
    decision: str = Field(pattern="^(cleared|to_report|reported)$")
    note: str = Field(default="", max_length=1000)


@router.post("/activities/{activity_id}/review")
def review(activity_id: int, body: ReviewIn, admin: User = Depends(require_admin),
           db: Session = Depends(get_db)):
    """AML-021 合规官复核。

    `reported` 只是**记录合规官已经报送**，代码不会替他向任何外部系统发送——
    报送要人判断、要签字，自动报送既不合规也不负责任。
    """
    result = service.review(db, activity_id, admin.id, body.decision, body.note)
    from app.modules.admin.router import record_audit

    record_audit(db, admin.id, "aml_review", "suspicious_activity", activity_id,
                 f"复核结论 {body.decision}")
    return result
