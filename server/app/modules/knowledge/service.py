"""知识库（06）：经验采集（事件驱动）+ 估价参考 + 模板检索 + FAQ。"""
import statistics

from sqlalchemy.orm import Session

from app.core.events import subscribe

from .models import DecompositionTemplate, FaqEntry, KnowledgeCard

# 冷启动种子（KB 冷启动策略：人工模板兜底，标注来源）
# AI-DEC-040（V132，106 号 spec）每一步都带「交付物」与「验收标准」：
# 没有这两样的节点不能算叶子——说不出交什么、怎么验，就无法托管也无法验收。
SEED_TEMPLATES = [
    {
        "category": "软件开发",
        "keywords": ["网站", "小程序", "app", "系统", "开发"],
        "items": [
            {"title": "需求梳理与原型设计", "skills": ["产品设计"], "budget_ratio_bps": 1500, "depends_on": [],
             "deliverable": "需求文档与可点击原型", "acceptance": "发布方逐页确认原型覆盖了全部需求点"},
            {"title": "UI 视觉设计", "skills": ["UI设计"], "budget_ratio_bps": 1500, "depends_on": [0],
             "deliverable": "全部页面的视觉稿与切图", "acceptance": "视觉稿页面数与原型一致，发布方确认风格"},
            {"title": "前端开发", "skills": ["前端开发"], "budget_ratio_bps": 2500, "depends_on": [1],
             "deliverable": "可部署的前端代码与构建说明", "acceptance": "在测试环境按原型逐页走通，与视觉稿一致"},
            {"title": "后端开发", "skills": ["后端开发"], "budget_ratio_bps": 2500, "depends_on": [0],
             "deliverable": "接口服务代码、接口文档与部署说明", "acceptance": "接口文档里的每个接口在测试环境可调用并返回约定结构"},
            {"title": "联调测试与上线", "skills": ["测试"], "budget_ratio_bps": 2000, "depends_on": [2, 3],
             "deliverable": "测试报告与线上可访问的地址", "acceptance": "测试报告无未关闭的严重缺陷，线上地址可正常使用"},
        ],
    },
    {
        "category": "活动策划",
        "keywords": ["活动", "策划", "开业", "婚礼"],
        "items": [
            {"title": "方案策划与预算", "skills": ["策划"], "budget_ratio_bps": 2000, "depends_on": [],
             "deliverable": "活动方案与分项预算表", "acceptance": "发布方确认方案与预算"},
            {"title": "物料设计制作", "skills": ["设计"], "budget_ratio_bps": 3000, "depends_on": [0],
             "deliverable": "方案列出的全部物料实物或印刷文件", "acceptance": "物料清单逐项点验，数量与规格相符"},
            {"title": "现场执行", "skills": ["活动执行"], "budget_ratio_bps": 5000, "depends_on": [1],
             "deliverable": "按方案完成的活动与现场照片", "acceptance": "活动按方案时间与流程完成，发布方现场或凭照片确认"},
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
    """KB-021 估价参考：返回分布而非单点值（可解释性要求）。

    KB-013 数据新鲜度：仅统计近 180 天闭环数据，过时价格自动淘汰。
    """
    from datetime import timedelta

    from app.modules.account.models import utcnow

    freshness_cutoff = utcnow() - timedelta(days=180)
    query = db.query(KnowledgeCard).filter(
        KnowledgeCard.category == category, KnowledgeCard.outcome == "completed",
        KnowledgeCard.price_actual_cents > 0,
        KnowledgeCard.created_at >= freshness_cutoff,
    )
    if city:
        query = query.filter(KnowledgeCard.city == city)
    from app.modules.task.models import Task

    # KB-064（266 号 spec）连同发布方一起取（同一条查询，不逐张查）
    rows = (query.outerjoin(Task, Task.id == KnowledgeCard.source_task_id)
            .with_entities(KnowledgeCard.id, KnowledgeCard.price_actual_cents, Task.creator_id).all())
    prices = [r.price_actual_cents for r in rows]
    if not prices:
        return {"sample_size": 0, "message": "暂无同类闭环数据，建议参考平台模板报价"}
    return {
        "sample_size": len(prices),
        "p50_cents": int(statistics.median(prices)),
        "min_cents": min(prices),
        "max_cents": max(prices),
        **_by_publisher(rows),
    }


# KB-064 最大的一位发布方占到这么多样本，就提醒「中位价被他拉着走」
CONCENTRATED_SHARE = 0.5
CONCENTRATED_MIN_SAMPLES = 3


def _by_publisher(rows) -> dict:
    """KB-064（266 号 spec）经验卡去重：同一位发布方反复发同类任务，会让中位价变成「他一个人的价」。
    每位发布方先取自己的中位价、算一个样本，再取中位——原来的 sample_size / p50 不变，另给去重后的数。
    找不到来源任务的卡各算一位（不硬猜是谁发的）。只给人数与比例，不给是谁。"""
    groups: dict = {}
    for r in rows:
        groups.setdefault(("u", r.creator_id) if r.creator_id is not None else ("card", r.id), []).append(r.price_actual_cents)
    per = [statistics.median(v) for v in groups.values()]
    top = max(len(v) for v in groups.values())
    share = round(top / len(rows), 3)
    concentrated = len(rows) >= CONCENTRATED_MIN_SAMPLES and share > CONCENTRATED_SHARE
    p50 = int(statistics.median(per))
    note = (f"这 {len(rows)} 单里有 {top} 单来自同一位发布方；按发布方去重后，{len(groups)} 位发布方的中位价是 "
            f"¥{p50 / 100:.2f}，更能代表行情" if concentrated else "")
    return {"publishers": len(groups), "p50_by_publisher_cents": p50, "top_publisher_share": share,
            "concentrated": concentrated, "note": note}


def find_template(db: Session, category: str, text: str) -> dict | None:
    """KB-020 分解模板检索：先精确类目，后关键词命中。"""
    tpl = db.query(DecompositionTemplate).filter(DecompositionTemplate.category == category).first()
    if tpl:
        return {"category": tpl.category, "items": tpl.items, "source": "seed_template"}
    for tpl in db.query(DecompositionTemplate).all():
        if any(kw in text for kw in tpl.keywords):
            return {"category": tpl.category, "items": tpl.items, "source": "keyword_match"}
    # 闭环任务沉淀的分解结构（KB-001 → AI-DEC-012 反哺）
    # 「decomposition 非空」在 Python 里判断，不写进 SQL：`json != json` 在 SQLite 上能跑，
    # 在 Postgres 上**没有这个运算符**——V132 在本地 Postgres 上跑拆解测试才撞见：
    # 没有种子模板、也没命中关键词的类目，生产上一发起分解就 500。
    # 只看最近 20 张：要的是最新的那份成功拆法，不是全表扫描。
    recent = (
        db.query(KnowledgeCard)
        .filter(KnowledgeCard.category == category)
        .order_by(KnowledgeCard.id.desc())
        .limit(20)
        .all()
    )
    card = next((c for c in recent if c.decomposition), None)
    if card:
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
    # 只给真正有人干过活的任务建卡：容器步骤（逐层拆解的中间层）自己不干活，
    # 它的结项是子步骤推导出来的，不是一条独立的经验
    if task.executor_id is None and not db.query(Task.id).filter(Task.parent_id == task.id).first():
        return
    days = 0
    if task.completed_at and task.created_at:
        days = max((task.completed_at - task.created_at).days, 0)
    # 脱敏（KB-002/060）：类目/城市/价格/工期是结构化的，本来就不含个人信息；
    # 而 `title` 是**用户自己打的字**——探针实测它带着姓名、门牌号和手机号，
    # 而这张卡通过 `/knowledge/cards` 给别的用户看。
    # 这行注释以前就在这儿，做脱敏的东西不在。
    from app.core.scrub import party_names, scrub_text

    card = KnowledgeCard(
        source_task_id=task.id,
        category=task.category,
        city=task.city,
        # 不存用户打的标题：这张卡的用途是「按类目/城市看价格与工期」，
        # 标题对它没有必要，而它是这条链上唯一的自由文本——
        # **最可靠的脱敏是不采集**（最小必要原则）。
        title=f"{task.category}·{task.city or '不限城市'}",
        price_actual_cents=task.budget_cents,
        duration_days=days,
        # KB-072b 失败率是子类的属性：经过纠纷才结项的，单独记成 disputed
        outcome="disputed" if _had_dispute(db, task.id) else "completed",
    )
    # 母任务闭环时快照子任务分解结构，反哺模板（AI-DEC-012）
    children = db.query(Task).filter(Task.parent_id == task.id).all()
    if children:
        names = party_names(db, task)
        card.decomposition = [
            {"title": scrub_text(c.title, names), "skills": c.required_skills,
             "budget_ratio_bps": c.budget_cents * 10000 // max(task.budget_cents, 1),
             "depends_on": c.depends_on}
            for c in children
        ]
    db.add(card)


def _had_dispute(db: Session, task_id: int) -> bool:
    from app.modules.dispute.models import Dispute

    return db.query(Dispute.id).filter(Dispute.task_id == task_id).first() is not None


def _on_task_cancelled(db: Session, payload: dict) -> None:
    """KB-072b 取消也是经验：只记**有人接过**的（成交后取消），没人接的草稿撤回不是经验。"""
    from app.modules.task.models import Task

    task = db.get(Task, payload["task_id"])
    if not task or task.executor_id is None:
        return
    if db.query(KnowledgeCard.id).filter(KnowledgeCard.source_task_id == task.id).first():
        return
    db.add(KnowledgeCard(
        source_task_id=task.id, category=task.category, city=task.city,
        title=f"{task.category}·{task.city or '不限城市'}",
        price_actual_cents=task.budget_cents, duration_days=0, outcome="cancelled",
    ))


def register_event_handlers() -> None:
    subscribe("task.completed", _on_task_completed, retry=True)
    subscribe("task.cancelled", _on_task_cancelled, retry=True)
