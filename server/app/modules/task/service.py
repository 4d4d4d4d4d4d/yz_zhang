"""任务状态机与审核（03）。"""
from sqlalchemy.orm import Session

from app.core.errors import bad_request, conflict
from app.core.events import publish

from .models import TRANSITIONS, Task

# TASK-004 发布前机审违禁词（RISK-001 简化实现；生产接内容安全服务）
BANNED_WORDS = ["代考", "刷单", "赌博", "毒品", "枪支", "色情", "洗钱"]

# OPS-004 类目种子（首次启动写入 Category 表，此后运营后台维护）
SEED_CATEGORIES = [
    {"name": "保洁"}, {"name": "跑腿"}, {"name": "维修"}, {"name": "软件开发"},
    {"name": "设计"}, {"name": "活动策划"}, {"name": "二手交易"},
    # LAW-003 律师市场 / 高危作业准入（ACC-022）
    {"name": "法律咨询", "required_cert": "律师"},
    {"name": "电工维修", "required_cert": "电工"},
    {"name": "燃气维修", "required_cert": "燃气作业"},
]


SEED_CITIES = ["上海", "北京", "深圳", "杭州"]

# TASK-003 高频类目发布模板（配合 KB-021 参考价组成模板库）
TASK_TEMPLATES = {
    "保洁": {"title": "日常保洁（X 室 X 厅）", "description": "面积约 __ ㎡；重点：厨房/卫生间深度清洁；需自带工具", "checklist": ["确认面积与户型", "是否需要自带工具", "验收标准拍照对比"]},
    "跑腿": {"title": "帮取/帮送（同城）", "description": "取件地址：__；送达地址：__；物品：__；时效要求：__", "checklist": ["物品是否易碎/贵重", "时效要求", "费用是否含跑腿费外的垫付"]},
    "维修": {"title": "上门维修（品类）", "description": "故障描述：__；品牌型号：__；期望上门时间：__", "checklist": ["故障照片", "是否含配件费", "保修约定"]},
    "软件开发": {"title": "开发需求（一句话概括）", "description": "目标用户：__；核心功能：__；交付物：源码+部署文档；验收标准：__", "checklist": ["建议用 AI 分解为里程碑", "明确验收标准", "约定源码归属"]},
}


def seed_categories(db: Session) -> None:
    from .models import Category, City

    if not db.query(Category).first():
        for c in SEED_CATEGORIES:
            db.add(Category(**c))
    if not db.query(City).first():
        for name in SEED_CITIES:
            db.add(City(name=name))
    db.flush()


def validate_city(db: Session, task) -> None:
    """GEO-030：线下任务城市必须已开通。"""
    from .models import City

    if task.is_remote or not task.city:
        return
    city = db.query(City).filter(City.name == task.city).first()
    if not city or not city.active:
        raise bad_request(f"城市「{task.city}」尚未开通服务", "city_not_open")


def get_category(db: Session, name: str):
    from .models import Category

    return db.query(Category).filter(Category.name == name).first()


def check_category_qualification(db: Session, task, user) -> None:
    """ACC-022 受限类目准入（读类目表，运营后台可配）。"""
    category = get_category(db, task.category)
    required = category.required_cert if category else ""
    if required and required not in (user.certifications or []):
        raise bad_request(f"该类目需「{required}」职业资质认证后方可接单", "certification_required")


def check_executor_capacity(db: Session, user_id: int) -> None:
    """TASK-011 并发接单上限：在途单（成交/执行/待验收）达上限后不可再接。"""
    from app.core.config import settings

    active = (
        db.query(Task)
        .filter(Task.executor_id == user_id,
                Task.status.in_(("matched", "in_progress", "pending_acceptance")))
        .count()
    )
    if active >= settings.MAX_ACTIVE_TASKS:
        raise conflict(
            f"在途任务已达上限（{settings.MAX_ACTIVE_TASKS} 单），请先完成现有任务", "capacity_full"
        )


def validate_category(db: Session, name: str) -> None:
    category = get_category(db, name)
    if not category or not category.active:
        raise bad_request(f"类目「{name}」不存在或已停用", "invalid_category")


def machine_review(text: str) -> str | None:
    for word in BANNED_WORDS:
        if word in text:
            return word
    return None


def transition(db: Session, task: Task, new_status: str, event_payload: dict | None = None):
    """唯一合法的状态变更入口（统一审计 + 事件派发）。"""
    allowed = TRANSITIONS.get(task.status, set())
    if new_status not in allowed:
        raise conflict(f"任务状态不允许从 {task.status} 变更为 {new_status}", "invalid_transition")
    old = task.status
    task.status = new_status
    db.add(task)
    db.flush()
    publish(db, f"task.{new_status}", {"task_id": task.id, "from": old, **(event_payload or {})})


def validate_publishable(task: Task, db: Session | None = None) -> None:
    if db is not None:
        validate_city(db, task)  # GEO-030
    if task.budget_cents <= 0:
        raise bad_request("预算必须大于 0", "budget_required")
    hit = machine_review(task.title + " " + task.description)
    if hit:
        raise bad_request(f"内容含违禁信息（{hit}），发布被拒绝", "content_rejected")
    if not task.is_remote and (task.lat is None or task.lng is None):
        raise bad_request("线下任务必须提供位置", "location_required")
    if task.deadline is not None:
        from app.modules.account.models import utcnow

        deadline = task.deadline
        if deadline.tzinfo is not None:
            deadline = deadline.replace(tzinfo=None)
        if deadline <= utcnow():
            raise bad_request("截止时间必须晚于当前时间", "deadline_in_past")
