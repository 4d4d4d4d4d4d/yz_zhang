from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.modules.account.models import utcnow


class KnowledgeCard(Base):
    """KB-001 闭环任务经验卡（脱敏后的结构化经验）。"""

    __tablename__ = "knowledge_cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_task_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    category: Mapped[str] = mapped_column(String(50), index=True)
    city: Mapped[str] = mapped_column(String(50), default="", index=True)
    title: Mapped[str] = mapped_column(String(120), default="")
    price_actual_cents: Mapped[int] = mapped_column(Integer, default=0)
    duration_days: Mapped[int] = mapped_column(Integer, default=0)
    outcome: Mapped[str] = mapped_column(String(20), default="completed")  # completed/disputed/cancelled
    # 若为母任务：分解结构快照（AI-DEC-012 模板来源）
    decomposition: Mapped[list] = mapped_column(JSON, default=list)
    # KB-011 向量索引。`embedding_model` 一起存：换模型后旧向量不可比，
    # 必须能识别出「这条是旧模型算的」才能增量重建，而不是全表重跑或者
    # 拿两个模型的向量做余弦（那会得到一堆毫无意义的相似度）。
    embedding: Mapped[list] = mapped_column(JSON, default=list)
    embedding_model: Mapped[str] = mapped_column(String(40), default="")
    # KB-070（V134，108 号 spec）样本是证据，子类是结论，结论必须能回溯到证据
    cluster_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    # pending 未处理 / assigned 已并入 / undecided 待定区（运营判）/ held 阈值缺失或模型不符
    # / excluded 风控标记不进 / retracted 已撤回
    cluster_state: Mapped[str] = mapped_column(String(12), default="pending", index=True)
    # 待定区里最像的那个子类与相似度，给运营判断用
    cluster_hint: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class KnowledgeCluster(Base):
    """KB-070 子类：知识图谱的节点。样本只是挂在它下面的证据（94 号 spec）。

    质心、样本数与结果构成**增量**维护；价格与工期分布、共识与分歧在读的时候
    从成员样本算——成员是有界的，算出来是精确值，而增量维护分位数做不到精确。
    """

    __tablename__ = "knowledge_clusters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category: Mapped[str] = mapped_column(String(50), index=True)
    label: Mapped[str] = mapped_column(String(120))
    centroid: Mapped[list] = mapped_column(JSON, default=list)
    embedding_model: Mapped[str] = mapped_column(String(40), default="")
    sample_count: Mapped[int] = mapped_column(Integer, default=0)
    # {"completed": n, "disputed": n, "cancelled": n}——失败率是子类的属性，不是噪音
    outcome_counts: Mapped[dict] = mapped_column(JSON, default=dict)
    # active / merged / retired
    status: Mapped[str] = mapped_column(String(12), default="active", index=True)
    merged_into: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 谁建的：auto（语义模型下自动新建）/ ops:<admin id>（运营从待定区建）
    created_by: Mapped[str] = mapped_column(String(20), default="auto")
    last_sample_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ClusterThreshold(Base):
    """KB-071 按大类标定的归并阈值。不许是写死的数字：换 embedding 模型就得重标。"""

    __tablename__ = "knowledge_cluster_thresholds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category: Mapped[str] = mapped_column(String(50), unique=True)
    tau_merge: Mapped[float] = mapped_column(Float)
    tau_near: Mapped[float] = mapped_column(Float)
    embedding_model: Mapped[str] = mapped_column(String(40))
    # 标定依据：几对人工标注、误判几对、谁标的、什么时候
    labeled_pairs: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[int] = mapped_column(Integer, default=0)
    calibrated_by: Mapped[int] = mapped_column(Integer)
    calibrated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ReusableUnit(Base):
    """KB-080 可复用单元：从子类蒸馏出来、有契约的经验（109 号 spec，设计见 95 号）。

    88 号对经验资产的四条要求逐条落成字段：有来源（cluster_id + sample_ids）、
    有适用条件（applicability，**含排除条件**）、有验证结果（validation）、
    有使用权限（scope + reuse_license / train_license 两个独立的位）。
    """

    __tablename__ = "reusable_units"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cluster_id: Mapped[int] = mapped_column(Integer, index=True)
    # price_hint / checklist / procedure / skill_tool —— 风险递增
    kind: Mapped[str] = mapped_column(String(16), index=True)
    title: Mapped[str] = mapped_column(String(120))
    version: Mapped[int] = mapped_column(Integer, default=1)
    content: Mapped[dict] = mapped_column(JSON, default=dict)
    # {category, cities, budget_min_cents, budget_max_cents, exclusions: [..]}
    applicability: Mapped[dict] = mapped_column(JSON, default=dict)
    sample_ids: Mapped[list] = mapped_column(JSON, default=list)
    # {status: unvalidated/validated/needs_review, uses, closed, reworked, failed}
    validation: Mapped[dict] = mapped_column(JSON, default=dict)
    scope: Mapped[str] = mapped_column(String(12), default="platform")
    reuse_license: Mapped[bool] = mapped_column(Boolean, default=False)
    train_license: Mapped[bool] = mapped_column(Boolean, default=False)
    # AGT-080 skill_tool 的声明：读什么、写什么、是否花钱、是否对外发消息
    manifest: Mapped[dict] = mapped_column(JSON, default=dict)
    est_cost_cents: Mapped[int] = mapped_column(Integer, default=0)
    # active / needs_review / retired
    status: Mapped[str] = mapped_column(String(14), default="active", index=True)
    created_by: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class UnitInvocation(Base):
    """KB-083 / AGT-082 每次调用留痕：谁、哪个单元的哪个版本、在什么场景、结果如何。"""

    __tablename__ = "unit_invocations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    unit_id: Mapped[int] = mapped_column(Integer, index=True)
    version: Mapped[int] = mapped_column(Integer)
    scenario: Mapped[str] = mapped_column(String(24))
    caller_id: Mapped[int] = mapped_column(Integer, index=True)
    task_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    input_summary: Mapped[str] = mapped_column(String(300), default="")
    output: Mapped[dict] = mapped_column(JSON, default=dict)
    cost_cents: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    # KB-084 结果回流：pending / closed / reworked / failed
    outcome: Mapped[str] = mapped_column(String(10), default="pending", index=True)
    # KB-085 这次调用的受益贡献者（调用当时已授权的人）
    beneficiaries: Mapped[list] = mapped_column(JSON, default=list)
    draft: Mapped[bool] = mapped_column(Boolean, default=False)
    discarded: Mapped[bool] = mapped_column(Boolean, default=False)
    # KB-089 来源被撤回：草稿不追回，但要标出来
    source_revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class DecompositionTemplate(Base):
    """KB 冷启动种子模板（运营维护，OPS-004）。"""

    __tablename__ = "decomposition_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category: Mapped[str] = mapped_column(String(50), index=True)
    keywords: Mapped[list] = mapped_column(JSON, default=list)
    items: Mapped[list] = mapped_column(JSON, default=list)  # [{title, description, skills, budget_ratio_bps, depends_on: [idx]}]


class FaqEntry(Base):
    """KB-005 平台 FAQ（智能客服知识来源）。"""

    __tablename__ = "faq_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    question: Mapped[str] = mapped_column(String(200))
    answer: Mapped[str] = mapped_column(Text)
    keywords: Mapped[list] = mapped_column(JSON, default=list)
    # KB-011 同上：FAQ 也进向量索引，客服检索才不必依赖人工维护关键词表
    embedding: Mapped[list] = mapped_column(JSON, default=list)
    embedding_model: Mapped[str] = mapped_column(String(40), default="")
