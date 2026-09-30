"""KB-060 经验数据的脱敏（83 号 spec）。

探针（V108）：两处经验管线的 docstring 都写着「脱敏」，而两处都存着用户原文。

    KnowledgeCard 的 docstring：「闭环任务经验卡（脱敏后的结构化经验）」
    落库的 title：给王芳家搬钢琴 朝阳区幸福小区3号楼502 联系13800138000
    别的用户读经验卡：200，能读到含手机号的卡：True

    _record_lesson 的 docstring：「脱敏：不写 user_id、不写精确地址、不写金额」
    拼出来的系统提示词里：含手机号 True、含姓名 True、含地址 True

也就是说：一个客户的电话与门牌号，(a) 通过经验卡端点给了**别的用户**，
(b) 通过提示词给了**第三方模型**。这不是数据质量问题，是
《个人信息保护法》的最小必要与目的限制——写在注释里的「脱敏」，
没有任何东西在做。

这里只做一件事：**一个函数，在写入点被调用**。和 `LEDGER_KINDS` 同一种做法——
不在四十个地方各自记得脱敏，而是让不脱敏的路径根本不存在。
"""
import re

# 手机号 / 身份证 / 银行卡的模式复用日志脱敏那一份（DEP-040），
# **不另写一套**：两套正则迟早会不一致，而不一致的那一条就是漏出去的那条。
from app.core.observability import _PATTERNS as _NUMERIC_PATTERNS

# 邮箱：整体替换，保留域名会暴露雇主/学校
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")

# 门牌号一类：数字紧跟这些量词时，数字本身就是精确位置。
# 「朝阳区」这种行政区不动——城市与区是经验里有用的部分（价格随地段变），
# 而「3号楼502」不是：它精确到一户人家。
_ADDRESS = re.compile(
    r"\d+\s*(?:号楼|号院|单元|室|层|楼|门|栋|幢|座)"
)
# 「某某路 8 号」里的门牌数字
_HOUSE_NO = re.compile(r"(?<=[路街巷道])\s*\d+\s*号?")
# 小区 / 楼盘名：它比行政区精确得多，基本等价于「哪一片住户」。
# **行政区（市/区）刻意保留**——价格与工期随地段变，那是经验里有用的部分；
# 精确到一个小区就不是了。
# 名字里不许跨过「市/区/县」：否则 `[\u4e00-\u9fa5]{2,10}小区` 会把
# 「朝阳区幸福小区」整段吃掉，连行政区一起抹了——而行政区是要留的
_COMPOUND = re.compile(
    r"(?:(?![市区县])[\u4e00-\u9fa5A-Za-z0-9]){2,10}(?:小区|花园|公寓|大厦|苑|湾)(?![市区县])"
)

MASK = "〔已脱敏〕"

# 数字类整段抹掉，**不用日志那种保留头尾的掩码**。
# 日志里 `138****8000` 是对的：运维要靠头尾把几条日志对上。
# 而经验数据是给**别的用户**和**第三方模型**看的，末四位加城市常常
# 已经足够定位到人——留头尾在这里不是折中，是漏。
_FULL_PHONE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_FULL_ID = re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")
_FULL_CARD = re.compile(r"(?<!\d)\d{16,19}(?!\d)")


def scrub_text(text: str, names: tuple[str, ...] = ()) -> str:
    """把一段自由文本里的个人信息去掉。

    `names` 是**平台已知的真实姓名**（当事双方的 `real_name`）：
    姓名没法靠正则认出来，但平台知道这一单是谁和谁——
    用它去替换，比写一个「中文姓名识别」准得多，也不会把「王府井」当成人名。
    """
    if not text:
        return text
    out = text
    for name in sorted({n for n in names if n and len(n) >= 2}, key=len, reverse=True):
        out = out.replace(name, MASK)
    out = _EMAIL.sub(MASK, out)
    out = _COMPOUND.sub(MASK, out)
    out = _ADDRESS.sub(MASK, out)
    out = _HOUSE_NO.sub(MASK, out)
    # 数字类放最后：前面的替换可能把数字带进 MASK，先做会互相干扰
    for pattern in (_FULL_PHONE, _FULL_ID, _FULL_CARD):
        out = pattern.sub(MASK, out)
    # 兜底：日志那套模式能认出来的残余（格式带分隔符的号码等）
    for pattern, repl in _NUMERIC_PATTERNS:
        out = pattern.sub(repl, out)
    return out


def party_names(db, task) -> tuple[str, ...]:
    """这一单的当事人真实姓名。

    取不到就返回空——脱敏少一条也不该让主流程失败（经验回流是增强，
    不是交易的一部分）。
    """
    from app.modules.account.models import User

    ids = [i for i in (getattr(task, "creator_id", None),
                       getattr(task, "executor_id", None)) if i]
    if not ids:
        return ()
    rows = db.query(User).filter(User.id.in_(ids)).all()
    out: list[str] = []
    for u in rows:
        if u.real_name:
            out.append(u.real_name)
        if u.nickname:
            out.append(u.nickname)
    return tuple(out)
