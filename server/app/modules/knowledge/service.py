"""知识库（06）：经验采集（事件驱动）+ 估价参考 + 模板检索 + FAQ。"""
import statistics

from sqlalchemy.orm import Session

from app.core.events import subscribe

from .models import DecompositionTemplate, FaqEntry, KnowledgeCard

# 冷启动种子（KB 冷启动策略：人工模板兜底，标注来源）
SEED_TEMPLATES = [
    {
        "category": "软件开发",
        "keywords": ["网站", "小程序", "app", "系统", "开发"],
        "items": [
            {"title": "需求梳理与原型设计", "skills": ["产品设计"], "budget_ratio_bps": 1500, "depends_on": []},
            {"title": "UI 视觉设计", "skills": ["UI设计"], "budget_ratio_bps": 1500, "depends_on": [0]},
            {"title": "前端开发", "skills": ["前端开发"], "budget_ratio_bps": 2500, "depends_on": [1]},
            {"title": "后端开发", "skills": ["后端开发"], "budget_ratio_bps": 2500, "depends_on": [0]},
            {"title": "联调测试与上线", "skills": ["测试"], "budget_ratio_bps": 2000, "depends_on": [2, 3]},
        ],
    },
    {
        "category": "活动策划",
        "keywords": ["活动", "策划", "开业", "婚礼"],
        "items": [
            {"title": "方案策划与预算", "skills": ["策划"], "budget_ratio_bps": 2000, "depends_on": []},
            {"title": "物料设计制作", "skills": ["设计"], "budget_ratio_bps": 3000, "depends_on": [0]},
            {"title": "现场执行", "skills": ["活动执行"], "budget_ratio_bps": 5000, "depends_on": [1]},
        ],
    },
]

SEED_FAQS = [
    {"question": "平台如何收费", "answer": "任务成交后平台向执行者收取 8% 服务费，发布任务免费。", "keywords": ["收费", "佣金", "费率", "服务费"]},
    {"question": "资金托管安全吗", "answer": "成交后资金进入托管账户，验收通过才放款给执行者；发生纠纷时资金冻结，按仲裁结果分配。", "keywords": ["托管", "资金", "安全", "放款"]},
    {"question": "验收超时怎么办", "answer": "执行者提交验收后，发布者 3 天内未处理将自动验收并放款。", "keywords": ["验收", "超时", "自动"]},
    {"question": "如何发起纠纷", "answer": "在任务详情页点击发起纠纷，资金将被冻结，可先协商和解，协商不成由平台仲裁并自动执行裁决。", "keywords": ["纠纷", "仲裁", "投诉", "争议"]},
    {"question": "如何提现", "answer": "完成实名认证后，在钱包页发起提现，可用余额即时到账（模拟环境）。", "keywords": ["提现", "余额", "到账"]},
]


def seed(db: Session) -> None:
    if not db.query(DecompositionTemplate).first():
        for t in SEED_TEMPLATES:
            db.add(DecompositionTemplate(**t))
    if not db.query(FaqEntry).first():
        for f in SEED_FAQS:
            db.add(FaqEntry(**f))
    db.flush()


def price_reference(db: Session, category: str, city: str | None = None) -> dict:
    """KB-021 估价参考：返回分布而非单点值（可解释性要求）。"""
    query = db.query(KnowledgeCard).filter(
        KnowledgeCard.category == category, KnowledgeCard.outcome == "completed",
        KnowledgeCard.price_actual_cents > 0,
    )
    if city:
        query = query.filter(KnowledgeCard.city == city)
    prices = [c.price_actual_cents for c in query.all()]
    if not prices:
        return {"sample_size": 0, "message": "暂无同类闭环数据，建议参考平台模板报价"}
    return {
        "sample_size": len(prices),
        "p50_cents": int(statistics.median(prices)),
        "min_cents": min(prices),
        "max_cents": max(prices),
    }


def find_template(db: Session, category: str, text: str) -> dict | None:
    """KB-020 分解模板检索：先精确类目，后关键词命中。"""
    tpl = db.query(DecompositionTemplate).filter(DecompositionTemplate.category == category).first()
    if tpl:
        return {"category": tpl.category, "items": tpl.items, "source": "seed_template"}
    for tpl in db.query(DecompositionTemplate).all():
        if any(kw in text for kw in tpl.keywords):
            return {"category": tpl.category, "items": tpl.items, "source": "keyword_match"}
    # 闭环任务沉淀的分解结构（KB-001 → AI-DEC-012 反哺）
    card = (
        db.query(KnowledgeCard)
        .filter(KnowledgeCard.category == category, KnowledgeCard.decomposition != [])
        .order_by(KnowledgeCard.id.desc())
        .first()
    )
    if card and card.decomposition:
        return {"category": card.category, "items": card.decomposition, "source": "closed_loop_experience"}
    return None


def search_faq(db: Session, question: str) -> dict | None:
    """CS-002 简化版检索（生产为向量检索 + LLM 生成，此处关键词匹配保证可测）。"""
    best, best_hits = None, 0
    for faq in db.query(FaqEntry).all():
        hits = sum(1 for kw in faq.keywords if kw in question)
        if hits > best_hits:
            best, best_hits = faq, hits
    if not best:
        return None
    return {"question": best.question, "answer": best.answer, "source": "faq"}


# ---------- 事件订阅：任务闭环 → 经验入库（KB-001/TASK-035） ----------
def _on_task_completed(db: Session, payload: dict) -> None:
    from app.modules.task.models import Task

    task = db.get(Task, payload["task_id"])
    if not task:
        return
    days = 0
    if task.completed_at and task.created_at:
        days = max((task.completed_at - task.created_at).days, 0)
    # 脱敏（KB-002）：只保留类目/城市/价格/工期，不含个人信息与精确位置
    card = KnowledgeCard(
        source_task_id=task.id,
        category=task.category,
        city=task.city,
        title=task.title,
        price_actual_cents=task.budget_cents,
        duration_days=days,
        outcome="completed",
    )
    # 母任务闭环时快照子任务分解结构，反哺模板（AI-DEC-012）
    children = db.query(Task).filter(Task.parent_id == task.id).all()
    if children:
        card.decomposition = [
            {"title": c.title, "skills": c.required_skills,
             "budget_ratio_bps": c.budget_cents * 10000 // max(task.budget_cents, 1),
             "depends_on": c.depends_on}
            for c in children
        ]
    db.add(card)


def register_event_handlers() -> None:
    subscribe("task.completed", _on_task_completed)
