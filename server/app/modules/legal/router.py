"""法律模块（11.B）：LAW-001 法律信息 AI（合规底线：信息不构成意见）+ LAW-005 证据导出。"""
import hashlib
import json

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.errors import forbidden, not_found
from app.modules.account.models import User, utcnow
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
        "请先在平台发起纠纷处理；对平台处理决定不服的，可依合同争议解决条款提请约定的"
        "仲裁机构，或向有管辖权的法院起诉，平台可提供证据包导出。",
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


class DocumentIn(BaseModel):
    kind: str  # demand_letter 催告函 / settlement_agreement 和解协议
    task_id: int
    demand: str = Field(default="", max_length=500)  # 诉求（如：3 日内完成整改）


@router.post("/documents")
def generate_document(
    body: DocumentIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """LAW-002 文书模板生成：按任务/合约数据填充草稿（仅当事人；草稿需自行核对）。"""
    task = db.get(Task, body.task_id)
    if not task:
        raise not_found("任务不存在")
    if user.id not in (task.creator_id, task.executor_id):
        raise forbidden("仅任务当事人可生成文书")
    from app.modules.contract.models import Contract

    contract = db.query(Contract).filter(Contract.task_id == task.id).first()
    amount = (contract.amount_cents if contract else task.budget_cents) / 100
    counterparty = task.executor_id if user.id == task.creator_id else task.creator_id
    if body.kind == "demand_letter":
        text = (
            f"催告函\n\n"
            f"致 用户{counterparty}：\n"
            f"就平台任务《{task.title}》（任务编号 {task.id}，合约金额 {amount:.2f} 元），"
            f"你方未按约定履行义务。现郑重催告：{body.demand or '请于收到本函 3 日内履行合约义务'}。\n"
            f"逾期未履行的，本人将依据《平台争议处理规则》申请平台处理，"
            f"并保留提请仲裁或诉诸法律的权利。\n\n"
            f"催告人：用户{user.id}（实名认证）"
        )
    elif body.kind == "settlement_agreement":
        text = (
            f"和解协议（草稿）\n\n"
            f"甲方：用户{task.creator_id}　乙方：用户{task.executor_id}\n"
            f"就任务《{task.title}》（编号 {task.id}，托管金额 {amount:.2f} 元）产生的争议，"
            f"双方自愿达成如下和解：\n"
            f"一、结算方案：{body.demand or '[请填写分割比例或金额]'}；\n"
            f"二、款项由平台按本协议自动执行，执行完毕后双方互不追究；\n"
            f"三、本协议经双方在平台确认后生效。"
        )
    else:
        raise not_found("不支持的文书类型")
    return {"kind": body.kind, "text": text,
            "disclaimer": "本文书为模板草稿，重要事项请咨询执业律师后使用。"}


@router.get("/disputes/{dispute_id}/evidence-export")
def evidence_export(
    dispute_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """LAW-012/013/014 证据包导出：**一份自洽、可直接提交的材料**。

    与此前的区别是三点：
    1. 覆盖完整时间线（合同全文与签署、资金分账、执行留痕与图片凭证、
       纠纷答辩与处理决定），而不是只有纠纷那几个字段；
    2. 附哈希链验证报告与第三方存证回执；
    3. **诚实标注证明力边界**——哪些有第三方背书、哪些只是平台自算，
       写清楚好过让人误以为全部有司法效力。
    """
    from app.modules.anchor import service as anchor
    from app.modules.contract import service as contract_service
    from app.modules.contract.models import Contract
    from app.modules.dispute.models import DisputeStatement
    from app.modules.finance import service as finance
    from app.modules.task.models import ProgressLog

    dispute = db.get(Dispute, dispute_id)
    if not dispute:
        raise not_found("纠纷不存在")
    task = db.get(Task, dispute.task_id)
    if user.id not in (task.creator_id, task.executor_id) and not user.is_admin:
        raise forbidden("仅当事人可导出证据包")

    contract = db.query(Contract).filter(Contract.task_id == task.id).first()
    signatures = contract_service.verify_signatures(db, contract) if contract else None
    logs = db.query(ProgressLog).filter(ProgressLog.task_id == task.id) \
             .order_by(ProgressLog.id).all()
    statements = db.query(DisputeStatement).filter(
        DisputeStatement.dispute_id == dispute.id).order_by(DisputeStatement.id).all()

    package = {
        "dispute_id": dispute.id,
        "task": {
            "id": task.id, "title": task.title, "category": task.category,
            "budget_cents": task.budget_cents, "status": task.status,
            "creator_id": task.creator_id, "executor_id": task.executor_id,
        },
        "contract": {
            "id": contract.id, "version": contract.version,
            "amount_cents": contract.amount_cents,
            "released_cents": contract.released_cents,
            "status": contract.status, "terms": contract.terms,
        } if contract else None,
        "signatures": signatures,
        "settlements": finance.contract_trail(db, contract.id) if contract else [],
        "progress_logs": [
            {"id": r.id, "user_id": r.user_id, "kind": r.kind, "content": r.content,
             "images": r.images or [], "at": r.created_at.isoformat()}
            for r in logs
        ],
        "dispute": {
            "opened_by": dispute.opened_by, "reason": dispute.reason,
            "evidence": dispute.evidence, "status": dispute.status,
            "statements": [
                {"user_id": r.user_id, "role": r.role, "content": r.content,
                 "attachments": r.attachments or [], "at": r.created_at.isoformat()}
                for r in statements
            ],
            # LAW-021 用词：平台内部处理不是法律意义上的仲裁裁决
            "platform_decision": {
                "executor_share_bps": dispute.verdict_executor_share_bps,
                "reason": dispute.verdict_reason,
            },
        },
        "exported_by": user.id,
        "exported_at": utcnow().isoformat(),
    }
    canonical = json.dumps(package, ensure_ascii=False, sort_keys=True)
    chain = anchor.verify_chain(db)
    cov = anchor.coverage(db)

    return {
        "package": package,
        "sha256": hashlib.sha256(canonical.encode()).hexdigest(),
        "integrity": {
            "chain_valid": chain.get("valid"),
            "chain_entries": chain.get("total"),
            "third_party_backed_to_seq": cov["third_party_backed_to_seq"],
            "uncovered_entries": cov["uncovered_entries"],
            "receipts": cov["receipts"],
        },
        # LAW-013/021 证明力声明：写清楚这份材料能证明什么、不能证明什么
        "evidentiary_notice": {
            "signatures": signatures["reliability_note"] if signatures else "无合约签署记录。",
            "chain": cov["note"],
            "decision": (
                "本文所载「平台处理决定」系依当事人事先约定作出的合同履行调整，"
                "**不是法律意义上的仲裁裁决**，不具有强制执行力。"
                "对处理决定不服的，可依合同争议解决条款提请约定的仲裁机构"
                "或向有管辖权的法院提起诉讼。"
            ),
        },
    }
