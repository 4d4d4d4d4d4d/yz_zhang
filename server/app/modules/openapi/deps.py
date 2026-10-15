"""API Key 鉴权依赖（54 号 spec）。

**scope 校验在依赖层做，不在每个端点里写 if。**

写 if 的那种做法，新端点的默认状态是「没检查」而不是「拒绝」——
这与 V47 修的限流那个洞是同一个形状：当时限流只有 7 个手写调用点，
新端点默认裸奔。
"""
from fastapi import Depends, Header, Response
from sqlalchemy.orm import Session

from app.core import ratelimit
from app.core.db import get_db
from app.core.errors import forbidden, too_many_requests
from app.modules.account.models import User

from . import service
from .models import ApiKey


def api_principal(
    response: Response,
    db: Session = Depends(get_db, scope="function"), x_api_key: str = Header(default=""),
) -> tuple[ApiKey, User]:
    if not x_api_key:
        raise forbidden("缺少 X-API-Key", "api_key_required")
    key, user = service.resolve_key(db, x_api_key)
    # API-050 按 Key 独立限流（145 号 spec）：一个集成跑飞只耗它自己的额度，不挤占同一出口 IP 的其他人。
    # 回标准的 429 + Retry-After，集成方的 HTTP 客户端大多会自动退避
    limit = service.effective_rate(key)
    response.headers["X-RateLimit-Limit"] = str(limit)
    retry = ratelimit.hit(f"apikey:{key.id}", limit, 60)
    if retry is not None:
        raise too_many_requests(f"这把 API Key 每分钟最多 {limit} 次请求，请 {retry} 秒后重试；需要更高额度请联系平台",
                                "api_key_rate_limited", retry, {"X-RateLimit-Limit": str(limit)})
    return key, user


def require_scope(scope: str):
    """用法：`_=Depends(require_scope("tasks:read"))`。

    返回的是 (key, user) 元组，端点需要用户时直接取第二项。
    """

    def _dep(principal: tuple[ApiKey, User] = Depends(api_principal)):
        key, user = principal
        service.assert_scope(key, scope)
        return principal

    return _dep
