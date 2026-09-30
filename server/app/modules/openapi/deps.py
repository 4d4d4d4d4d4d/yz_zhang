"""API Key 鉴权依赖（54 号 spec）。

**scope 校验在依赖层做，不在每个端点里写 if。**

写 if 的那种做法，新端点的默认状态是「没检查」而不是「拒绝」——
这与 V47 修的限流那个洞是同一个形状：当时限流只有 7 个手写调用点，
新端点默认裸奔。
"""
from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import forbidden
from app.modules.account.models import User

from . import service
from .models import ApiKey


def api_principal(
    db: Session = Depends(get_db), x_api_key: str = Header(default=""),
) -> tuple[ApiKey, User]:
    if not x_api_key:
        raise forbidden("缺少 X-API-Key", "api_key_required")
    return service.resolve_key(db, x_api_key)


def require_scope(scope: str):
    """用法：`_=Depends(require_scope("tasks:read"))`。

    返回的是 (key, user) 元组，端点需要用户时直接取第二项。
    """

    def _dep(principal: tuple[ApiKey, User] = Depends(api_principal)):
        key, user = principal
        service.assert_scope(key, scope)
        return principal

    return _dep
