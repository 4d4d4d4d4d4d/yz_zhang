from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import forbidden
from app.core.security import decode_token
from app.modules.account.models import User


def get_current_user(
    db: Session = Depends(get_db), authorization: str = Header(default="")
) -> User:
    if not authorization.startswith("Bearer "):
        raise forbidden("未登录", "unauthenticated")
    try:
        payload = decode_token(authorization.removeprefix("Bearer "))
    except Exception:
        raise forbidden("登录态无效", "unauthenticated")
    user = db.get(User, int(payload["sub"]))
    if not user:
        raise forbidden("用户不存在", "unauthenticated")
    # ACC-005 会话吊销检查（旧 token 无 sid 的跳过，兼容期）
    if payload.get("sid") is not None:
        from app.modules.account.models import LoginSession

        session = db.get(LoginSession, int(payload["sid"]))
        if not session or session.revoked:
            raise forbidden("登录态已失效，请重新登录", "session_revoked")
    if user.is_banned:
        raise forbidden("账号已被封禁，如有异议请申诉", "account_banned")
    if user.is_deleted:
        raise forbidden("账号已注销", "account_deleted")
    return user


def require_verified(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> User:
    """ACC-020：接单/资金操作前强制实名。

    LAW-031/032：实名依赖证件信息（敏感个人信息）。用户撤回了证件同意，
    平台就不能再拿证件信息做责任主体确认——实名能力随之失效，
    这些动作也必须一起停下，否则「撤回」只是个不改变任何事的按钮。
    """
    if not user.is_verified:
        raise forbidden("需先完成实名认证", "verification_required")
    from app.modules.legal import consent

    # 这里不复用 consent.refuse_if_withdrawn：它抛 409（数据冲突），
    # 而「你自己关掉了这个能力」在语义上是 403（无权），错误码保持一致即可
    if consent.was_revoked(db, user.id, "identity") and not consent.has_consent(
        db, user.id, "identity"
    ):
        raise forbidden(
            "你已撤回对证件信息处理的同意，接单与资金操作已停用，可在 设置→隐私 重新授权",
            "consent_withdrawn",
        )
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise forbidden("需要管理员权限", "admin_required")
    return user


def require_job_auth(x_job_token: str = Header(default="")) -> None:
    """内部定时任务鉴权：cron 端点必须携带共享密钥（OPS-011）。

    这些 job（自动放款/合约作废/任务下架/对账等）会改动资金与状态，
    绝不能对外公开裸调用；生产由调度器带 X-Job-Token 触发。
    """
    from app.core.config import settings

    if not settings.JOB_TOKEN or x_job_token != settings.JOB_TOKEN:
        raise forbidden("无效的任务令牌", "invalid_job_token")
