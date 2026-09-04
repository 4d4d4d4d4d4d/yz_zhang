"""ACCDEL-020~027 账号注销时的个人信息处置：**逐字段声明，而不是逐字段手写**。

改造前，注销就是 `router.py` 里一段手写的赋值序列：

    user.phone = f"deleted:{user.id}"
    user.nickname = "已注销用户"
    user.real_name = ""
    user.bio = ""
    user.lat = None
    user.lng = None

六行，凭作者当时想得起来的字段。`skills` / `interests` / `certifications` /
`privacy` / `city` / `referral_code` 全部留着，`is_admin` 也留着；
`payout_accounts` 里一张完整银行卡号加持卡人姓名原样留下——
而同一段代码却小心地把 `users.real_name` 清成了空串。

不是「该不该留」的问题，是**没有人做过这个决定**。
以后每加一个字段，默认行为都是「留下」，且不会有任何测试变红。

## 为什么不是「一删了之」

直觉上「用户行使删除权 = 全删」，但删过头本身违法：

- 《反洗钱法》第十九条：客户身份资料自业务关系结束当年计起、交易记录自交易
  记账当年计起，**至少保存五年**；
- 《个人信息保护法》第四十七条给删除权留了例外：
  「法律、行政法规规定的保存期限未届满」的不删除，但应当**停止处理**。

所以处置是三选一（`Disposition`），每一列都必须在表里有明确归属。
`tests/test_account_deletion.py` 用反射逐列比对，多写或漏写都会红。
"""
from enum import Enum

from sqlalchemy.orm import Session

from .models import User


class Disposition(str, Enum):
    ERASE = "erase"    # 清空/置默认：没有任何法定留存义务的标识与画像
    MASK = "mask"      # 脱敏保留：够反洗钱调档与对账，不足以再用于业务
    RETAIN = "retain"  # 原样保留：法定义务、对方当事人的凭证、或系统主键


E, M, R = Disposition.ERASE, Disposition.MASK, Disposition.RETAIN

# ---------- users ----------
USER_DISPOSITION: dict[str, Disposition] = {
    "id": R,                    # 主键，全部流水的外键
    "phone": M,                 # → deleted:<id>（不可登录、不可检索；号码释放，见 ACCDEL-040）
    "password_hash": E,         # 凭据没有任何留存理由
    "nickname": M,              # → 已注销用户（历史合约/评价里需要一个署名占位）
    "bio": E,
    "city": E,
    "lat": E,
    "lng": E,
    "skills": E,
    "interests": E,
    "certifications": E,
    "privacy": E,
    "service_rate_cents": E,
    "available_times": E,
    "accepting_orders": E,      # → False，别再进推荐池
    "is_verified": R,           # 「这个账户当年通过了实名」属于身份资料
    "real_name": M,             # ACCDEL-022 → 张*（清空既不满足留存，也没多买到隐私）
    "id_digest": R,             # 法定身份资料 + 一人一号防绕过；本身不可逆
    "id_masked": R,
    "is_adult": R,
    "is_admin": E,              # ACCDEL-024 注销一个管理员，管理员标记不能留着
    "is_banned": R,             # ACCDEL-025 注销不是洗白封禁的手段
    "is_deleted": R,            # 由注销流程置 True
    "referral_code": E,         # ACCDEL-026 注销后这个码不该还能被别人填
    "referred_by": R,           # 上线的返佣凭证
    "referral_rewarded": R,
    "credit_score": R,          # ACCDEL-027 以下四项是**交易对手方**的凭证
    "rating_sum": R,
    "rating_count": R,
    "tasks_completed": R,
    "created_at": R,
}

# ---------- payout_accounts ----------
PAYOUT_DISPOSITION: dict[str, Disposition] = {
    "user_id": R,
    "kind": R,
    "account_no": M,     # ACCDEL-023 → 6222****0123，脱敏后**不足以发起打款**（有意为之）
    "holder_name": M,    # → 张*
    "created_at": R,
}


def mask_name(name: str) -> str:
    """姓 + `*`：够对账时人工核对，不足以识别到人。"""
    if not name:
        return ""
    return name[0] + "*" * max(len(name) - 1, 1)


def mask_account_no(no: str) -> str:
    return no[:4] + "****" + no[-4:] if len(no) >= 8 else "****"


def erase_personal_data(db: Session, user: User) -> dict:
    """按处置表执行注销脱敏。**注销流程唯一的个人信息处置入口。**

    只做数据处置，不做资金/关系闸门——那是调用方（router）的职责，
    且必须在调用本函数**之前**完成：本函数执行后账号即不可逆。
    """
    from app.modules.wallet.models import PayoutAccount

    user.is_deleted = True
    user.phone = f"deleted:{user.id}"
    user.nickname = "已注销用户"
    user.real_name = mask_name(user.real_name)
    user.password_hash = ""
    user.bio = ""
    user.city = ""
    user.lat = None
    user.lng = None
    user.skills = []
    user.interests = []
    user.certifications = []
    user.privacy = {}
    user.service_rate_cents = 0
    user.available_times = ""
    user.accepting_orders = False
    user.is_admin = False
    user.referral_code = ""
    db.add(user)

    payout = db.get(PayoutAccount, user.id)
    if payout:
        payout.account_no = mask_account_no(payout.account_no)
        payout.holder_name = mask_name(payout.holder_name)
        db.add(payout)
    return {"payout_masked": payout is not None}
