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


# 后来加的类目：已有库里没有就补上（只补一次；补上之后运营可以停用，不会被重新打开）。
# 「财税」——OPC 服务包的发单模板与答不了时的去处（124 号 spec）
# 「宠物照护」「助老陪伴」——第四轮场景发掘的两个服务包的发单模板与去处（173 号 spec，V200）
# 「陪练看护」——服务对象是未成年人的陪练、看护、接送；接单要有审核通过的无犯罪记录证明（214 号 spec，V242）
# 「翻译」——自由译者服务包（259 号 spec，V286）
MINOR_CARE_CERT = "无犯罪记录证明"
# SCN-154（274 号 spec）接触直接入口食品的人每年体检、取得健康证明后方可上岗（食品安全法第四十五条）
HEALTH_CERT = "健康证明"
# SCN-160（286 号 spec）2 米以上可能坠落处的作业属特种作业，须持特种作业操作证（高处作业）上岗
HEIGHT_WORK_CERT = "高处作业操作证"
# SCN-176（302 号 spec）实习期上高速须由持相应驾驶证三年以上的驾驶人陪同；陪驾类目要审核通过的驾驶证
DRIVER_CERT = "驾驶证（三年以上驾龄）"
# SCN-194（319 号 spec）多地开锁业按特种行业管理，要到公安机关登记备案；上门开锁类目要审核通过的备案证明
LOCKSMITH_CERT = "开锁备案证明"
# SCN-199（325 号 spec）电工作业属特种作业：上门接电工活要审核通过的低压电工作业操作证
ELECTRICIAN_CERT = "低压电工作业操作证"
ADDED_CATEGORIES = [{"name": "财税"}, {"name": "宠物照护"}, {"name": "助老陪伴"},
                    {"name": "陪练看护", "required_cert": MINOR_CARE_CERT},
                    # 「翻译」——第七轮场景发掘的自由译者服务包的发单模板与去处（259 号 spec，V286）
                    {"name": "翻译"},
                    # 「整理收纳」「上门做饭」——第八轮场景发掘（274 号 spec，V298）；上门做饭要审核通过的健康证明
                    {"name": "整理收纳"}, {"name": "上门做饭", "required_cert": HEALTH_CERT},
                    # 「家电清洗」「空调外机拆装（高处作业）」——第九轮场景发掘（286 号 spec，V313）；后者要高处作业证
                    {"name": "家电清洗"}, {"name": "空调外机拆装（高处作业）", "required_cert": HEIGHT_WORK_CERT},
                    # 「活动跟拍」——第十轮场景发掘（294 号 spec，V321）
                    {"name": "活动跟拍"},
                    # 「情绪陪伴」「上门私教」——第十一轮场景发掘（298 号 spec，V325）
                    {"name": "情绪陪伴"}, {"name": "上门私教"},
                    # 「数码维修与回收」「陪驾」——第十二轮场景发掘（302 号 spec，V329）；陪驾要审核通过的驾驶证
                    {"name": "数码维修与回收"}, {"name": "陪驾", "required_cert": DRIVER_CERT},
                    # 「搬家」「母婴护理」——第十三轮场景发掘（306 号 spec，V333）；母婴护理要审核通过的健康证明
                    # SCN-181（307 号 spec）母婴护理照护的是新生儿：还要无犯罪记录证明（与陪练看护同一道关）
                    {"name": "搬家"}, {"name": "母婴护理", "required_cert": HEALTH_CERT, "extra_certs": [MINOR_CARE_CERT]},
                    # 「管道疏通」「求职辅导」——第十四轮场景发掘（310 号 spec，V337）
                    {"name": "管道疏通"}, {"name": "求职辅导"},
                    # 「老人助浴」「上门理发」——第十五轮场景发掘（313 号 spec，V340）；助浴要审核通过的健康证明
                    {"name": "老人助浴", "required_cert": HEALTH_CERT}, {"name": "上门理发"},
                    # 「废品回收」「电动车维修」——第十六轮场景发掘（316 号 spec，V343）
                    {"name": "废品回收"}, {"name": "电动车维修"},
                    # 「防水补漏」「上门开锁」——第十七轮场景发掘（319 号 spec，V346）；开锁要审核通过的备案证明
                    {"name": "防水补漏"}, {"name": "上门开锁", "required_cert": LOCKSMITH_CERT},
                    # 「陪诊」「家具安装」——第十八轮场景发掘（322 号 spec，V349）
                    {"name": "陪诊"}, {"name": "家具安装"},
                    # 「水电维修」「短视频剪辑」——第十九轮场景发掘（325 号 spec，V352）；水电维修要低压电工作业操作证
                    {"name": "水电维修", "required_cert": ELECTRICIAN_CERT}, {"name": "短视频剪辑"},
                    # 「上门跟妆」「网站小程序搭建」——第二十轮场景发掘（328 号 spec，V355）
                    {"name": "上门跟妆"}, {"name": "网站小程序搭建"}]

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
    for c in ADDED_CATEGORIES:
        if not db.query(Category.id).filter(Category.name == c["name"]).first():
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


def category_certs(category) -> list[str]:
    """SCN-181（307 号 spec）这个类目要的全部资质：required_cert 在前，再加 extra_certs（去空、去重）。"""
    if category is None:
        return []
    out: list[str] = []
    for c in [category.required_cert or "", *(category.extra_certs or [])]:
        c = (c or "").strip()
        if c and c not in out:
            out.append(c)
    return out


def check_category_qualification(db: Session, task, user) -> None:
    """ACC-022 受限类目准入（读类目表，运营后台可配）。SCN-181 类目可以要多张，张张都要有。"""
    category = get_category(db, task.category)
    required = category_certs(category)
    if not required and getattr(task, "minor_involved", False):
        required = [MINOR_CARE_CERT]        # SCN-144 服务对象是未成年人的单，不论哪个类目都要这份证明
    if not required:
        return
    # CERT-001/005 读的是**已核准且未过期**的资质，不是 user.certifications 里
    # 有没有这个名字。改造前那个字段是用户自己 POST 进去的，这道门一直是虚的。
    from app.modules.account import cert_service

    missing = [c for c in required if not cert_service.has_certification(db, user.id, c)]
    if not missing:
        return
    if len(required) == 1:
        raise bad_request(
            f"该类目需「{required[0]}」职业资质，请提交证件影像并通过平台核验后接单",
            "certification_required",
        )
    raise bad_request(
        f"该类目需{''.join(f'「{c}」' for c in required)}{len(required)} 项职业资质，你还缺"
        f"{''.join(f'「{c}」' for c in missing)}：请提交证件影像并通过平台核验后接单",
        "certification_required",
    )


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


def machine_review(text: str, db: Session | None = None) -> str | None:
    """TASK-004 / VND-030 内容机审：走 `ModerationProvider` 抽象。

    返回命中的标签（拒绝）或 None（放行）。本地实现即原违禁词表，
    换第三方内容安全只需改 `PLATFORM_MODERATION_PROVIDER`。

    CONC-067：第三方内容安全是一次网络调用。传入 `db` 时先把只读事务提交、连接还回池里；
    **调用方必须在写库之前机审**（先审后写），否则守卫会报——那是要改调用顺序，不是要绕过。
    """
    from app.vendors.registry import get_provider

    if db is not None:
        from app.vendors.base import release

        release(db)

    result = get_provider("moderation").check("text", text)
    if result.status == "reject":
        labels = result.data.get("labels") or []
        return labels[0] if labels else "违规内容"
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


def review_or_reject(db: Session, text: str) -> None:
    """先审后写：发布类请求在写任何一行之前调用。

    同一个会话里审过的同一段文字不再审第二次：外层（如机器发布在拿额度锁之前）已经先审过，
    里层的建单就不该在锁里再调一次外部服务。
    """
    import hashlib

    digest = hashlib.sha256(text.encode()).hexdigest()
    passed = db.info.setdefault("moderation_passed", set())
    if digest in passed:
        return
    hit = machine_review(text, db)
    if hit:
        raise bad_request(f"内容含违禁信息（{hit}），发布被拒绝", "content_rejected")
    passed.add(digest)


def validate_publishable(task: Task, db: Session | None = None, reviewed: bool = False) -> None:
    if db is not None:
        validate_city(db, task)  # GEO-030
    if task.budget_cents <= 0:
        raise bad_request("预算必须大于 0", "budget_required")
    # FIN-020/021 金融合规红线先于普通机审：涉众性金融不是「内容不当」，
    # 是平台根本不能做的业务，拒绝理由也必须说清楚为什么
    from app.modules.finance.compliance import assert_no_finance_offer, check_pricing

    check_pricing(task.pricing)
    assert_no_finance_offer(f"{task.title} {task.description}")
    from app.modules.task.k12 import assert_no_k12_tutoring

    assert_no_k12_tutoring(f"{task.title} {task.description}")   # SCN-143 中小学学科类家教不承接
    from app.modules.task.errand import assert_no_restricted_errand

    assert_no_restricted_errand(f"{task.title} {task.description}")   # SCN-164 代开处方药、倒卖号源，SCN-177 无证陪练学车不承接
    if not reviewed:
        hit = machine_review(task.title + " " + task.description, db)
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


def retime_slot(task: Task, start: str, end: str) -> None:
    """SCN-138 / SCN-139 名额改时段：时段与标题里的「（MM-DD 时段）」一起改。没有日期的任务只改时段。"""
    if task.work_date:
        md = f"{task.work_date.month:02d}-{task.work_date.day:02d}"
        old = f" {task.shift_start}–{task.shift_end}" if task.shift_start else ""
        new = f" {start}–{end}" if start else ""
        task.title = task.title.replace(f"（{md}{old}）", f"（{md}{new}）", 1)
    task.shift_start, task.shift_end = start, end
