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
# SCN-227（341 号 spec）医疗护理员培训合格后上岗（国家卫生健康委等 2019 年通知）；住院护工类目要审核通过的证明
CAREGIVER_CERT = "医疗护理员培训合格证明"
# SCN-233（343 号 spec）卖食品要有食品经营许可或当地的小作坊登记（《食品安全法》第三十五条），另要健康证明（第四十五条）
BAKERY_CERT = "食品经营许可证或小作坊登记证"
# SCN-245（352 号 spec）导游执业应当取得导游证（《旅游法》第三十七条）
GUIDE_CERT = "导游证"
# 游泳是高危险性体育项目——第三十五轮场景发掘（355 号 spec，V382）
SWIM_CERT = "游泳社会体育指导员证书"
# 燃气燃烧器具的安装维修要有资质——第三十八轮场景发掘（362 号 spec，V389）
GAS_CERT = "燃气具安装维修从业资格证明"
# 制冷与空调作业属特种作业（特种作业目录），加氟、焊管、修制冷系统要持操作证——第五十四轮场景发掘（397 号 spec，V424）
REFRIGERATION_CERT = "制冷与空调作业操作证"
# SCN-294b（407 号 spec）小型及以上无人机要操控员执照；消费级轻型机多数不要，所以做成发单人按这一单加选
DRONE_PILOT_CERT = "民用无人机操控员执照"
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
                    {"name": "上门跟妆"}, {"name": "网站小程序搭建"},
                    # 「文案写作」「监控安装」——第二十一轮场景发掘（331 号 spec，V358）
                    {"name": "文案写作"}, {"name": "监控安装"},
                    # 「证件照拍摄」「上门洗车」——第二十二轮场景发掘（333 号 spec，V360）
                    {"name": "证件照拍摄"}, {"name": "上门洗车"},
                    # 「账号代运营」「婚礼司仪」——第二十三轮场景发掘（335 号 spec，V362）
                    {"name": "账号代运营"}, {"name": "婚礼司仪"},
                    # 「插画约稿」「代驾」——第二十四轮场景发掘（337 号 spec，V364）；代驾与陪驾一样要审核通过的驾驶证
                    {"name": "插画约稿"}, {"name": "代驾", "required_cert": DRIVER_CERT},
                    # 「派对布置」「除甲醛治理」——第二十五轮场景发掘（339 号 spec，V366）
                    {"name": "派对布置"}, {"name": "除甲醛治理"},
                    # 「住院护工」「家电维修」——第二十六轮场景发掘（341 号 spec，V368）
                    {"name": "住院护工", "required_cert": CAREGIVER_CERT}, {"name": "家电维修"},
                    # 「宠物美容」「代办年检」——第二十七轮场景发掘（342 号 spec，V369）；代办年检要开别人的车，要审核通过的驾驶证
                    {"name": "宠物美容"}, {"name": "代办年检", "required_cert": DRIVER_CERT},
                    # 「配音」「私房烘焙」——第二十八轮场景发掘（343 号 spec，V370）；私房烘焙要经营许可（或小作坊登记）与健康证明
                    {"name": "配音"}, {"name": "私房烘焙", "required_cert": BAKERY_CERT, "extra_certs": [HEALTH_CERT]},
                    # 「地推传单」「汽车贴膜」——第二十九轮场景发掘（345 号 spec，V372）
                    {"name": "地推传单"}, {"name": "汽车贴膜"},
                    # 「上门宴席」「网店客服」——第三十轮场景发掘（346 号 spec，V373）；办宴席要健康证明
                    {"name": "上门宴席", "required_cert": HEALTH_CERT}, {"name": "网店客服"},
                    # 「上门按摩」「网络与智能家居」——第三十一轮场景发掘（347 号 spec，V374）
                    {"name": "上门按摩"}, {"name": "网络与智能家居"},
                    # 「开荒保洁」「二手车陪验」——第三十二轮场景发掘（349 号 spec，V376）
                    {"name": "开荒保洁"}, {"name": "二手车陪验"},
                    # 「宠物训犬」「地陪导游」——第三十三轮场景发掘（352 号 spec，V379）；地陪导游要审核通过的导游证
                    {"name": "宠物训犬"}, {"name": "地陪导游", "required_cert": GUIDE_CERT},
                    # 「婚恋介绍」——第三十四轮场景发掘（353 号 spec，V380）；同轮的接送孩子包复用「陪练看护」类目
                    {"name": "婚恋介绍"},
                    # 「游泳私教」「除虫灭鼠」——第三十五轮场景发掘（355 号 spec，V382）；游泳私教要审核通过的游泳社会体育指导员证书
                    {"name": "游泳私教", "required_cert": SWIM_CERT}, {"name": "除虫灭鼠"},
                    # 「改衣裁缝」「身后事协助」——第三十六轮场景发掘（358 号 spec，V385）
                    {"name": "改衣裁缝"}, {"name": "身后事协助"},
                    # 「验房」「窗帘安装」——第三十七轮场景发掘（360 号 spec，V387）
                    {"name": "验房"}, {"name": "窗帘安装"},
                    # 「燃气具安装」「外语陪练」——第三十八轮场景发掘（362 号 spec，V389）；燃气具安装要审核通过的从业资格证明
                    {"name": "燃气具安装", "required_cert": GAS_CERT}, {"name": "外语陪练"},
                    # 「智能门锁安装」「充电桩安装」——第三十九轮场景发掘（365 号 spec，V391）；充电桩动电，要审核通过的低压电工作业操作证
                    {"name": "智能门锁安装"}, {"name": "充电桩安装", "required_cert": ELECTRICIAN_CERT},
                    # 「钢琴调律」「闲置代卖」——第四十轮场景发掘（367 号 spec，V393）
                    {"name": "钢琴调律"}, {"name": "闲置代卖"},
                    # 「墙面刷漆」「宠物善终」——第四十一轮场景发掘（369 号 spec，V396）
                    {"name": "墙面刷漆"}, {"name": "宠物善终"},
                    # 「老照片修复」「净水器安装」——第四十二轮场景发掘（371 号 spec，V398）
                    {"name": "老照片修复"}, {"name": "净水器安装"},
                    # 「上门汽车保养」「绿植养护」——第四十三轮场景发掘（373 号 spec，V400）
                    {"name": "上门汽车保养"}, {"name": "绿植养护"},
                    # 「沙发床垫清洗」「PPT 设计」——第四十四轮场景发掘（375 号 spec，V402）
                    {"name": "沙发床垫清洗"}, {"name": "PPT 设计"},
                    # 「数据恢复」「上门美甲」——第四十五轮场景发掘（378 号 spec，V404）
                    {"name": "数据恢复"}, {"name": "上门美甲"},
                    # 「装修监理」「宠物接送」——第四十六轮场景发掘（380 号 spec，V407）
                    {"name": "装修监理"}, {"name": "宠物接送"},
                    # 「鞋包清洗」「表格整理」——第四十七轮场景发掘（383 号 spec，V409）
                    {"name": "鞋包清洗"}, {"name": "表格整理"},
                    # 「瓷砖美缝」「商品拍摄」——第四十八轮场景发掘（385 号 spec，V412）
                    {"name": "瓷砖美缝"}, {"name": "商品拍摄"},
                    # 「会议纪要」「家具翻新」——第四十九轮场景发掘（387 号 spec，V414）
                    {"name": "会议纪要"}, {"name": "家具翻新"},
                    # 「装修垃圾清运」「Logo 设计」——第五十轮场景发掘（389 号 spec，V416）
                    {"name": "装修垃圾清运"}, {"name": "Logo 设计"},
                    # 「回忆录整理」「陪同口译」——第五十一轮场景发掘（391 号 spec，V418）
                    {"name": "回忆录整理"}, {"name": "陪同口译"},
                    # 「纱窗更换」「地暖清洗」——第五十二轮场景发掘（393 号 spec，V420）
                    {"name": "纱窗更换"}, {"name": "地暖清洗"},
                    # 「宠物寄养」「搭电换胎」——第五十三轮场景发掘（395 号 spec，V422）
                    {"name": "宠物寄养"}, {"name": "搭电换胎"},
                    # 「空调加氟维修」「数据分析报告」——第五十四轮场景发掘（397 号 spec，V424）；前者要审核通过的制冷与空调作业操作证
                    {"name": "空调加氟维修", "required_cert": REFRIGERATION_CERT}, {"name": "数据分析报告"},
                    # 「室内设计出图」「婚礼策划」——第五十五轮场景发掘（398 号 spec，V425）
                    {"name": "室内设计出图"}, {"name": "婚礼策划"},
                    # 「网店代发货打包」「用户访谈」——第五十六轮场景发掘（400 号 spec，V427）
                    {"name": "网店代发货打包"}, {"name": "用户访谈"},
                    # 「无人机航拍」「电脑组装与重装」——第五十七轮场景发掘（403 号 spec，V430）
                    {"name": "无人机航拍", "optional_certs": [DRONE_PILOT_CERT]}, {"name": "电脑组装与重装"},
                    # 「展台搭建」「外卖店铺代运营」——第五十八轮场景发掘（406 号 spec，V433）
                    {"name": "展台搭建", "optional_certs": [HEIGHT_WORK_CERT, ELECTRICIAN_CERT]}, {"name": "外卖店铺代运营"},
                    # 「居家适老化改造」「社区团购分拣配送」——第五十九轮场景发掘（409 号 spec，V436）
                    {"name": "居家适老化改造"}, {"name": "社区团购分拣配送"},
                    # 「团建活动执行」「寻宠服务」——第六十轮场景发掘（412 号 spec，V439）
                    {"name": "团建活动执行"}, {"name": "寻宠服务"},
                    # 「庭院绿化养护」「高空外窗外墙清洗」——第六十一轮场景发掘（415 号 spec，V442）；后者要审核通过的高处作业操作证
                    {"name": "庭院绿化养护"}, {"name": "高空外窗外墙清洗", "required_cert": HEIGHT_WORK_CERT},
                    # 「电视投影挂装」「空置房屋代看护」——第六十二轮场景发掘（417 号 spec，V444）
                    {"name": "电视投影挂装"}, {"name": "空置房屋代看护"},
                    # 「志愿填报咨询」「户外徒步领队」——第六十三轮场景发掘（419 号 spec，V446）
                    {"name": "志愿填报咨询"}, {"name": "户外徒步领队"},
                    # 「门头招牌安装」「活动音响灯光」——第六十四轮场景发掘（421 号 spec，V448）；发单人可按这一单加选高处作业证、电工证（SCN-294b）
                    {"name": "门头招牌安装", "optional_certs": [HEIGHT_WORK_CERT, ELECTRICIAN_CERT]},
                    {"name": "活动音响灯光", "optional_certs": [ELECTRICIAN_CERT]},
                    # 「上门取送洗衣」「老人助餐送餐」——第六十五轮场景发掘（424 号 spec，V451）
                    {"name": "上门取送洗衣"}, {"name": "老人助餐送餐"},
                    # 「代祭扫」「办公设备维修」——第六十六轮场景发掘（425 号 spec，V452）
                    {"name": "代祭扫"}, {"name": "办公设备维修"},
                    # 「民宿退房保洁」「露营搭建」——第六十七轮场景发掘（427 号 spec，V454）
                    {"name": "民宿退房保洁"}, {"name": "露营搭建"},
                    # 「太阳能热水器清洗维修」「老录像带转数字」——第六十八轮场景发掘（428 号 spec，V455）；前者可加选高处作业证、电工证
                    {"name": "太阳能热水器清洗维修", "optional_certs": [HEIGHT_WORK_CERT, ELECTRICIAN_CERT]},
                    {"name": "老录像带转数字"},
                    # 「新生儿上门摄影」「儿童居家安全防护安装」——第六十九轮场景发掘（429 号 spec，V456）
                    {"name": "新生儿上门摄影"}, {"name": "儿童居家安全防护安装"},
                    # 「淋浴房安装」「智能马桶安装」——第七十轮场景发掘（430 号 spec，V457）；后者新拉插座可加选电工证
                    {"name": "淋浴房安装"}, {"name": "智能马桶安装", "optional_certs": [ELECTRICIAN_CERT]},
                    # 「远程电脑协助」「电动晾衣架安装」——第七十一轮场景发掘（431 号 spec，V458）；后者新拉线路可加选电工证
                    {"name": "远程电脑协助"}, {"name": "电动晾衣架安装", "optional_certs": [ELECTRICIAN_CERT]}]

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
        row = db.query(Category).filter(Category.name == c["name"]).first()
        if row is None:
            db.add(Category(**c))
        elif c.get("optional_certs") and not row.optional_certs:
            # SCN-294b（407 号 spec）已经在库里的类目补上可加选的资质；运营改过的不动
            row.optional_certs = list(c["optional_certs"])
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


def task_required_certs(db: Session, task) -> tuple[list[str], bool]:
    """接这一单要的全部资质，以及其中有没有发单人加选的（报名准入与推荐共用这一份，不各算各的）。

    类目要的（SCN-181 可多张）；没有时服务对象是未成年人要无犯罪记录证明（SCN-144）；
    再加发单人为这一单加选的（SCN-294b，407 号）。"""
    required = category_certs(get_category(db, task.category))
    if not required and getattr(task, "minor_involved", False):
        required = [MINOR_CARE_CERT]        # SCN-144 服务对象是未成年人的单，不论哪个类目都要这份证明
    task_certs = [c for c in (getattr(task, "task_certs", None) or []) if c and c not in required]
    return [*required, *task_certs], bool(task_certs)


def holders_of(db: Session, user_ids: list[int], required: list[str]) -> set[int]:
    """SCN-294d（408 号 spec）这些人里，张张资质都有（审核通过、未过期、认别名）的是谁——一次查完，不按人逐个查。"""
    if not required or not user_ids:
        return set(user_ids)
    from app.modules.account import cert_service
    from app.modules.account.models_cert import CertificationApplication

    now = cert_service.utcnow()
    have: dict[int, set[str]] = {}
    for r in (db.query(CertificationApplication)
              .filter(CertificationApplication.user_id.in_(user_ids), CertificationApplication.status == "approved").all()):
        if r.expires_at is None or r.expires_at > now:
            have.setdefault(r.user_id, set()).add(r.name)
    alias = {c: cert_service.cert_aliases(c, db) for c in required}
    return {uid for uid in user_ids if all(alias[c] & have.get(uid, set()) for c in required)}


def check_category_qualification(db: Session, task, user) -> None:
    """ACC-022 受限类目准入（读类目表，运营后台可配）。SCN-181 类目可以要多张，张张都要有。
    SCN-294b（407 号 spec）发单人为这一单加选的资质（task_certs）也要都有。"""
    required, added = task_required_certs(db, task)
    if not required:
        return
    scope = "这一单" if added else "该类目"
    # CERT-001/005 读的是**已核准且未过期**的资质，不是 user.certifications 里
    # 有没有这个名字。改造前那个字段是用户自己 POST 进去的，这道门一直是虚的。
    from app.modules.account import cert_service

    missing = [c for c in required if not cert_service.has_certification(db, user.id, c)]
    if not missing:
        return
    if len(required) == 1:
        # SCN-212 同一张证有别的叫法的，说一声持那个名字的也行（没有别名的类目一字不变）
        others = sorted(cert_service.cert_aliases(required[0], db) - {required[0]})
        alias = f"（持{''.join(f'「{c}」' for c in others)}也可以）" if others else ""
        raise bad_request(
            f"{scope}需「{required[0]}」职业资质{alias}，请提交证件影像并通过平台核验后接单",
            "certification_required",
        )
    raise bad_request(
        f"{scope}需{''.join(f'「{c}」' for c in required)}{len(required)} 项职业资质，你还缺"
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

    # SCN-219 运营复核通过的这段文字放行一单（发出去就记在这一单上）
    assert_no_restricted_errand(f"{task.title} {task.description}", db, task.creator_id, task.id)   # SCN-164 代开处方药、倒卖号源，SCN-177 无证陪练学车不承接
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
    if db is not None:
        # SCN-219 所有校验都过了、要发出去了，才把复核记在这一单上（写库放在调审核供应商之后：CONC-067）
        from app.modules.task.errand_reviews import bind_review

        bind_review(db, task.creator_id, f"{task.title} {task.description}", task.id)


def retime_slot(task: Task, start: str, end: str) -> None:
    """SCN-138 / SCN-139 名额改时段：时段与标题里的「（MM-DD 时段）」一起改。没有日期的任务只改时段。"""
    if task.work_date:
        md = f"{task.work_date.month:02d}-{task.work_date.day:02d}"
        old = f" {task.shift_start}–{task.shift_end}" if task.shift_start else ""
        new = f" {start}–{end}" if start else ""
        task.title = task.title.replace(f"（{md}{old}）", f"（{md}{new}）", 1)
    task.shift_start, task.shift_end = start, end
