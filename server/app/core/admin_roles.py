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


def roles_of(user: User) -> set[str]:
    """生效的角色。没分配过角色的管理员按 super 对待（见模块说明）。"""
    if not user.is_admin:
        return set()
    granted = {r for r in (user.admin_roles or []) if r in ROLES}
    return granted or {"super"}


def has_role(user: User, *roles: str) -> bool:
    mine = roles_of(user)
    return "super" in mine or bool(mine & set(roles))


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
