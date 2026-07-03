"""法律模块（11.B）：LAW-001 法律信息 AI（合规底线：信息不构成意见）+ LAW-005 证据导出。"""
import hashlib
import json

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.errors import forbidden, not_found
from app.modules.account.models import User
from app.modules.dispute.models import Dispute
from app.modules.task.models import Task

router = APIRouter(prefix="/legal", tags=["legal"])

DISCLAIMER = "以上内容仅为一般性法律信息，不构成法律意见；正式法律服务请咨询执业律师。"

# LAW-001 法律常识库（生产为 RAG + 审查层，此处规则实现保证可测与不编造）
LEGAL_FAQS = [
    {
        "keywords": ["合同", "合约", "效力", "有效"],
        "answer": "平台电子合约经双方在线确认签署后成立。依据《民法典》第四百六十九条，"
        "以电子数据交换等方式能够有形地表现所载内容的形式订立的合同视为书面形式。",
    },
    {
        "keywords": ["欠款", "不付款", "拖欠", "追讨"],
        "answer": "平台任务资金采用先托管后放款机制，正常情况下不存在拖欠。如对结算有争议，"
        "请先在平台发起纠纷仲裁；对裁决不服可向有管辖权的法院起诉，平台可提供证据包导出。",
    },
    {
        "keywords": ["劳动关系", "雇佣", "社保", "工伤"],
        "answer": "平台执行者与发布者之间一般构成承揽/委托关系而非劳动关系，"
        "具体认定以实际用工形态为准。涉及人身伤害的线下任务建议投保意外险。",
    },
    {
        "keywords": ["隐私", "个人信息", "泄露"],
        "answer": "依据《个人信息保护法》，你有权要求平台删除个人信息、导出个人数据。"
        "可在 设置→隐私 中操作，或联系客服提交请求。",
    },
]

# 高风险问题：直接引导专业渠道（11.C AI 输出强制审查层）
HIGH_RISK_KEYWORDS = ["杀", "自杀", "绑架", "人身安全", "威胁", "报警", "刑事"]


class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=500)


@router.post("/ask")
def legal_ask(body: AskIn, user: User = Depends(get_current_user)):
    if any(kw in body.question for kw in HIGH_RISK_KEYWORDS):
        return {
            "answer": "该问题涉及人身安全或刑事风险，请立即拨打 110 报警或联系专业机构，平台 AI 不提供此类解答。",
            "disclaimer": DISCLAIMER,
            "refused": True,
        }
    best, best_hits = None, 0
    for faq in LEGAL_FAQS:
        hits = sum(1 for kw in faq["keywords"] if kw in body.question)
        if hits > best_hits:
            best, best_hits = faq, hits
    if not best:
        return {
            "answer": "该问题超出平台法律知识库范围，建议通过「找律师」发布法律咨询任务，由执业律师解答。",
            "disclaimer": DISCLAIMER,
            "refused": True,
        }
    return {"answer": best["answer"], "disclaimer": DISCLAIMER, "refused": False}


@router.get("/disputes/{dispute_id}/evidence-export")
def evidence_export(
    dispute_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """LAW-005 证据包导出：结构化证据 + SHA256 哈希（防篡改校验，SC-011 存证雏形）。"""
    dispute = db.get(Dispute, dispute_id)
    if not dispute:
        raise not_found("纠纷不存在")
    task = db.get(Task, dispute.task_id)
    if user.id not in (task.creator_id, task.executor_id) and not user.is_admin:
        raise forbidden("仅当事人可导出证据包")
    package = {
        "dispute_id": dispute.id,
        "task_id": dispute.task_id,
        "task_title": task.title,
        "opened_by": dispute.opened_by,
        "reason": dispute.reason,
        "evidence": dispute.evidence,
        "verdict": {
            "executor_share_bps": dispute.verdict_executor_share_bps,
            "reason": dispute.verdict_reason,
        },
        "exported_by": user.id,
        "exported_at": dispute.created_at.isoformat(),
    }
    canonical = json.dumps(package, ensure_ascii=False, sort_keys=True)
    return {"package": package, "sha256": hashlib.sha256(canonical.encode()).hexdigest()}
