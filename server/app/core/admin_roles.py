"""SEC-061b 管理员分级（141 号 spec）。

此前管理员只有一个 `is_admin` 位：客服能批提现、运营能裁纠纷、谁都能撤销别人的资质。
V139 把读私聊与证件影像改成「写明理由 + 审计」——那是**事后**可查；这里补的是**事前**按职责拦。

角色按职责划分（最小权限、职责分离）：
- 一个管理员可以有几个角色；`super` 包含全部，并且只有它能给别人分配角色；
- **没分配过角色的管理员按 `super` 对待**（兼容此前的全部管理员与运维脚本），后台「管理员与角色」把他们标成「未分级」，
  上线前应当逐个分好——这一条写进 141 号 spec 的上线清单；
- 每一个管理员接口都必须声明自己属于哪些角色（`require_role`），闸门 `tests/test_admin_roles.py` 逐个核对。
"""
from __future__ import annotations

from fastapi import Depends

from app.core.deps import require_admin
from app.core.errors import forbidden
from app.modules.account.models import User

ROLES: dict[str, str] = {
    "super": "超级管理员：全部权限，并且能给管理员分配角色",
    "support": "客服：工单、举报、查用户",
    "arbiter": "仲裁：纠纷裁决与申诉复核；为举证查看私聊与材料（写明理由、进审计）",
    "compliance": "合规：资质与团队企业核验、上传审核、反洗钱、封禁与解封、安全看板、审计日志",
    "finance": "财务：提现审批、平台财务与结算、结算核对、代扣台账、补贴池注资",
    "ops": "运营：类目、城市、撮合参数、公告、增长活动、知识库、场景包、端侧模型、技能概念、平台 AI 助理",
}
# 任何一个管理员都能用的（只读的总览类）：仍然要显式声明，闸门才分得清「有意放开」和「忘了分」
ANY = tuple(ROLES)


def temporary_expired(user: User, role: str, now=None) -> bool:
    """SEC-061e（171 号 spec）这个角色是临时授予的、并且已经过了到期时间。"""
    until = (user.admin_role_until or {}).get(role)
    if not until:
        return False
    from datetime import datetime

    from app.modules.account.models import utcnow

    return datetime.fromisoformat(until.replace("Z", "+00:00")).replace(tzinfo=None) <= (now or utcnow())


def roles_of(user: User) -> set[str]:
    """生效的角色。没分配过角色的管理员按 super 对待（见模块说明）。

    SEC-061e 临时角色到期就不算。**分配过角色、但全部到期了的，是「没有角色」，不是「未分级」**——
    否则临时角色一到期，人就变成了超级管理员（临时授予本来就只能加在有长期角色的人身上，这里再兜一层）。"""
    if not user.is_admin:
        return set()
    assigned = {r for r in (user.admin_roles or []) if r in ROLES}
    live = {r for r in assigned if not temporary_expired(user, r)}
    if assigned and not live:
        return set()
    return live or {"super"}


def has_role(user: User, *roles: str) -> bool:
    mine = roles_of(user)
    return "super" in mine or bool(mine & set(roles))


# SEC-061f / PAY-042c 四眼的级别（155 号 spec）：超级管理员高于其他角色。第二位确认人的级别不能低于第一位——
# 超级管理员先批的，由普通财务「确认」，等于下级给上级盖章，复核形同虚设
RANK = {"super": 2}


def rank(user: User) -> int:
    return max((RANK.get(r, 1) for r in roles_of(user)), default=0)


def check_second_approver(first: User | None, second: User, amount_cents: int) -> None:
    """四眼第二步的人选：金额达到超管确认线时必须是超级管理员；任何金额下级别都不能低于第一位。"""
    from app.core.config import settings
    from app.core.errors import forbidden

    line = settings.SUPER_SECOND_APPROVAL_CENTS
    if amount_cents >= line and "super" not in roles_of(second):
        raise forbidden(f"达到 ¥{line / 100:.2f} 的出款，第二位确认人必须是超级管理员；请转交超级管理员确认",
                        "second_approver_role")
    # SEC-061g（284 号 spec）第二档：第一位也得是超级管理员（两位超级管理员先后确认）
    top = settings.DUAL_SUPER_APPROVAL_CENTS
    # （没有记录第一位的老调用照旧，只看第二位）
    if amount_cents >= top and first is not None and "super" not in roles_of(first):
        raise forbidden(f"达到 ¥{top / 100:.2f} 的出款要两位超级管理员先后确认：第一位不是超级管理员，"
                        "请驳回后由超级管理员重新发起 / 复核", "dual_super_required")
    if first is not None and rank(second) < rank(first):
        raise forbidden("第二位确认人的级别不能低于第一位：第一次复核是超级管理员，请由另一位超级管理员确认",
                        "second_approver_rank")


def labels(roles) -> str:
    return "、".join(ROLES[r].split("：")[0] for r in roles if r in ROLES)


def require_role(*roles: str):
    """管理员接口的依赖：先是管理员（`admin_required`），再看角色（`admin_role_required`）。"""
    unknown = set(roles) - set(ROLES)
    if unknown or not roles:
        raise ValueError(f"未知的管理员角色：{sorted(unknown)}")

    def role_dep(user: User = Depends(require_admin)) -> User:
        if not has_role(user, *roles):
            raise forbidden(f"这件事需要「{labels(roles)}」角色的管理员；你的角色是「{labels(sorted(roles_of(user)))}」。"
                            "需要的话请超级管理员在后台「管理员与角色」里给你加上", "admin_role_required")
        return user

    role_dep._roles = tuple(roles)   # 闸门读这个
    return role_dep
