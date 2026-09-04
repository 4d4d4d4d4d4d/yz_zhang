"""LAW-030~032/005 协议版本化、单独同意与数据主体权利（26 号 spec 第 D 节）。

> **补的是我自己留下的洞**：V50 把 `AGREEMENT_VERSION` 加进了配置，
> 却从未被任何代码读过——正是「存了但从不使用」这个模式（AIO-003 批评过同款）。
>
> PIPL 的三条硬要求：
> 1. 协议**版本化**，变更需**重新同意**（记录同意时间与版本）；
> 2. 敏感个人信息（证件、位置、支付）必须**单独同意**，不能藏在总协议里；
> 3. 数据主体权利：查询 / 更正 / 导出 / 删除 / **撤回同意**。
"""
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.errors import bad_request, conflict
from app.modules.account.models import utcnow

# LAW-030 三份文书独立成文、独立版本
DOCUMENTS = {
    "user_terms": "用户协议",
    "privacy_policy": "隐私政策",
    "platform_rules": "平台规则",
}

# LAW-031 敏感个人信息处理项：每一项都必须**单独告知 + 单独同意**。
# 把它们塞进总协议是 PIPL 明确禁止的做法。
SENSITIVE_SCOPES = {
    "identity": "身份证件信息（实名认证、防一人多号、纠纷时的责任主体确认）",
    "location": "精确位置信息（附近任务检索、到场打卡核验）",
    "payment": "支付与收款账户信息（资金结算、提现打款、反洗钱核验）",
}


class UserConsent(Base):
    """一条同意记录：谁、何时、对哪份文书/哪个敏感项、基于哪个版本。

    只增不改：撤回同意是**新增一条 revoked 记录**，而不是删掉原记录——
    「他当时确实同意过」本身就是需要保存的事实。
    """

    __tablename__ = "user_consents"
    __table_args__ = (
        UniqueConstraint("user_id", "scope", "version", "revoked_at",
                         name="uq_consent_user_scope_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    # 文书 key（user_terms/…）或敏感项 key（identity/location/payment）
    scope: Mapped[str] = mapped_column(String(24), index=True)
    version: Mapped[str] = mapped_column(String(24))
    # 同意时展示给用户的告知文本摘要——举证时要能说清「他看到的是什么」
    notice: Mapped[str] = mapped_column(Text, default="")
    granted_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


def current_version() -> str:
    from app.core.config import settings

    return settings.AGREEMENT_VERSION


def grant(db, user_id: int, scope: str, notice: str = "") -> UserConsent | None:
    """记录一次同意（幂等：同版本已同意则不重复记）。"""
    version = current_version()
    existing = (
        db.query(UserConsent)
        .filter(UserConsent.user_id == user_id, UserConsent.scope == scope,
                UserConsent.version == version, UserConsent.revoked_at.is_(None))
        .first()
    )
    if existing:
        return existing
    row = UserConsent(user_id=user_id, scope=scope, version=version,
                      notice=notice or _default_notice(scope))
    db.add(row)
    db.flush()
    return row


def _default_notice(scope: str) -> str:
    if scope in SENSITIVE_SCOPES:
        return f"处理{SENSITIVE_SCOPES[scope]}，用于上述目的，可随时撤回。"
    return f"同意《{DOCUMENTS.get(scope, scope)}》（版本 {current_version()}）。"


def has_consent(db, user_id: int, scope: str, version: str | None = None) -> bool:
    q = db.query(UserConsent).filter(
        UserConsent.user_id == user_id, UserConsent.scope == scope,
        UserConsent.revoked_at.is_(None),
    )
    if version:
        q = q.filter(UserConsent.version == version)
    return q.first() is not None


def grant_registration_consents(db, user_id: int) -> None:
    """LAW-030 注册即同意三份文书（注册页展示协议，业界标准做法）。

    刻意**不**要求注册后再点一次「我同意」：那既不增加法律效力，
    也只会让用户多点一次。真正有意义的是**版本变更后重新同意**。
    敏感项（证件/位置/支付）**不在此列**——它们必须单独同意。
    """
    for key in DOCUMENTS:
        grant(db, user_id, key)


def outdated_documents(db, user_id: int) -> list[str]:
    """LAW-030 返回用户尚未同意当前版本的文书。"""
    version = current_version()
    return [k for k in DOCUMENTS if not has_consent(db, user_id, k, version)]


def require_current_agreement(db, user_id: int) -> None:
    """协议更新后，**关键动作**前必须重新同意。

    刻意只拦关键动作（发布/接单/资金），不拦全站——否则用户连协议本身
    和注销入口都打不开，那是把合规做成了拒绝服务。
    """
    stale = outdated_documents(db, user_id)
    if stale:
        names = "、".join(DOCUMENTS[k] for k in stale)
        raise conflict(
            f"《{names}》已更新（版本 {current_version()}），请阅读并重新同意后继续",
            "agreement_update_required",
        )


def refuse_if_withdrawn(db, user_id: int, scope: str) -> None:
    """LAW-032 撤回过且未重新授权 → 拒绝继续处理该项敏感信息。

    刻意**不**拦「从未同意过」：那种情况下更具体的业务校验会给出更有用的提示
    （比如「你还没绑收款账户」），在它前面插一句「请先同意支付信息处理」
    只会把用户支到一个没东西可点的设置页。
    """
    if scope not in SENSITIVE_SCOPES:
        raise bad_request(f"未知的敏感信息范围 {scope}", "invalid_scope")
    if has_consent(db, user_id, scope) or not was_revoked(db, user_id, scope):
        return
    raise conflict(
        f"你已撤回对「{SENSITIVE_SCOPES[scope]}」的同意，需重新授权后才能继续",
        "consent_withdrawn",
    )


def was_revoked(db, user_id: int, scope: str) -> bool:
    """曾经同意过、但已撤回。撤回过和从没同意过必须区分开——见 ensure()。"""
    return (
        db.query(UserConsent)
        .filter(UserConsent.user_id == user_id, UserConsent.scope == scope,
                UserConsent.revoked_at.isnot(None))
        .first()
        is not None
    )


def ensure(db, user_id: int, scope: str) -> None:
    """LAW-031 敏感项的「随动作同意」：首次即记录，撤回后即拒绝。

    为什么不一律用 `require_sensitive_consent`：证件、收款账户、打卡定位这些，
    用户**提交这个动作本身**就是单独告知后的单独同意（表单页展示该项告知），
    再逼他先去设置页点一次「我同意」只是多一次点击，不增加任何法律效力。

    但**撤回之后必须真的停止处理**——这才是 PIPL 第十五条里最常被违反的一条，
    也是这个函数存在的意义：撤回过的项不会被下一次动作悄悄「自动重新同意」，
    必须用户再次显式授权（POST /legal/consents/{scope}/grant）。

    诚实的边界：服务端只能记录「他做了这个动作」，无法证明客户端确实展示了告知文本；
    真要举证到这一步，需客户端回传所展示告知的版本号，那是客户端合规的活。
    """
    refuse_if_withdrawn(db, user_id, scope)
    if not has_consent(db, user_id, scope):
        grant(db, user_id, scope)


def accept_documents(db, user_id: int) -> dict:
    """LAW-030 重新同意当前版本的全部基础文书。"""
    for key in DOCUMENTS:
        grant(db, user_id, key)
    return {"accepted_version": current_version(), "documents": list(DOCUMENTS)}


def grant_sensitive(db, user_id: int, scope: str) -> dict:
    """LAW-031/032 用户在设置页显式（重新）授权某个敏感项。"""
    if scope not in SENSITIVE_SCOPES:
        raise bad_request(f"未知的敏感信息范围 {scope}", "invalid_scope")
    grant(db, user_id, scope)
    return {"scope": scope, "granted": True, "version": current_version()}


def revoke(db, user_id: int, scope: str) -> dict:
    """LAW-032 撤回同意。

    撤回**敏感项**是用户的法定权利；撤回**基础协议**则等同于终止服务关系，
    应走注销流程而不是在这里悄悄断掉——所以这里明确拒绝并指路。
    """
    if scope in DOCUMENTS:
        raise bad_request(
            "撤回基础协议等同于终止服务关系，请使用账号注销功能（会先校验无未结资金与纠纷）",
            "use_account_deactivation",
        )
    if scope not in SENSITIVE_SCOPES:
        raise bad_request(f"未知的同意项 {scope}", "invalid_scope")
    rows = (
        db.query(UserConsent)
        .filter(UserConsent.user_id == user_id, UserConsent.scope == scope,
                UserConsent.revoked_at.is_(None))
        .all()
    )
    if not rows:
        raise conflict("尚未同意该项，无需撤回", "not_consented")
    now = utcnow()
    for row in rows:
        row.revoked_at = now
        db.add(row)
    db.flush()
    return {"scope": scope, "revoked": True,
            "effect": _revocation_effect(scope)}


def _revocation_effect(scope: str) -> str:
    """撤回后会失去什么——**必须提前说清楚**，否则用户点完才发现接不了单。"""
    return {
        "identity": "撤回后将无法接单、提现与发起纠纷（实名是这些能力的前提）；已完成的交易记录依法保留。",
        "location": "撤回后无法使用「附近任务」与到场打卡（进行中的线下任务将无法完成打卡），"
                    "可手动选择城市浏览；已结束任务的坐标会被清空，"
                    "进行中/纠纷中任务的打卡坐标依法保留至争议解决完毕。",
        "payment": "撤回后无法提现与收款；已绑定的收款账户将被解绑。",
    }[scope]


def status(db, user_id: int) -> dict:
    """LAW-032 数据主体权利页：我同意过什么、哪些待重新同意、能撤回什么。"""
    version = current_version()
    rows = db.query(UserConsent).filter(UserConsent.user_id == user_id).all()
    by_scope: dict[str, UserConsent] = {}
    for row in rows:
        if row.revoked_at is None:
            by_scope[row.scope] = row

    documents = [
        {"key": k, "name": name, "current_version": version,
         "agreed_version": by_scope[k].version if k in by_scope else None,
         "needs_reconsent": k not in by_scope or by_scope[k].version != version}
        for k, name in DOCUMENTS.items()
    ]
    sensitive = [
        {"key": k, "purpose": purpose,
         "granted": k in by_scope,
         "granted_at": by_scope[k].granted_at.isoformat() if k in by_scope else None,
         "revocable": True,
         "revocation_effect": _revocation_effect(k)}
        for k, purpose in SENSITIVE_SCOPES.items()
    ]
    return {
        "current_version": version,
        "documents": documents,
        "sensitive_scopes": sensitive,
        # LAW-032 数据主体权利入口（前端据此渲染，避免「有能力但用户找不到」）
        "rights": {
            "access": "GET /api/v1/users/me",
            "export": "GET /api/v1/users/me/export",
            "rectify": "PATCH /api/v1/users/me",
            "erase": "POST /api/v1/users/me/deactivate",
            "withdraw_consent": "POST /api/v1/legal/consents/{scope}/revoke",
        },
    }
