"""CERT 资质准入判定与申请处理（51 号 spec）。"""
from sqlalchemy.orm import Session

from app.core.errors import bad_request, conflict
from app.modules.account.models import User, utcnow

from .models_cert import CertificationApplication


def active_certifications(db: Session, user_id: int) -> list[str]:
    """CERT-005 **有效且未过期**的资质名单——准入判断读的是这个，
    不是 `user.certifications` 里有没有这个名字。

    过期的记录不删（要留痕），只是不再满足准入。
    """
    now = utcnow()
    rows = (
        db.query(CertificationApplication)
        .filter(CertificationApplication.user_id == user_id,
                CertificationApplication.status == "approved")
        .all()
    )
    return sorted({
        r.name for r in rows
        if r.expires_at is None or r.expires_at > now
    })


def has_certification(db: Session, user_id: int, name: str) -> bool:
    return name in active_certifications(db, user_id)


def submit(db: Session, user: User, *, name: str, holder_name: str, cert_number: str,
           issuer: str, expires_at, images: list[str]) -> CertificationApplication:
    """CERT-001 提交的是**申请**，不是资质。

    在管理员通过之前，`user.certifications` 一个字都不加。
    """
    if not user.is_verified:
        raise conflict("需先完成实名认证", "verification_required")
    # CERT-002 没有影像，审核员看什么
    if not images:
        raise bad_request("需上传证件影像后再提交", "images_required")
    # CERT-003 一张别人的电工证也是一张真证件
    if holder_name.strip() != (user.real_name or "").strip():
        raise bad_request(
            "证件持有人姓名与实名信息不一致，无法受理。"
            "职业资质必须由本人持有。",
            "holder_mismatch",
        )
    if expires_at is not None and expires_at <= utcnow():
        raise bad_request("证件已过期，请提交在有效期内的证件", "certificate_expired")
    # CERT-012 同一资质不能堆待审申请
    dup = (
        db.query(CertificationApplication)
        .filter(CertificationApplication.user_id == user.id,
                CertificationApplication.name == name,
                CertificationApplication.status == "pending")
        .first()
    )
    if dup:
        raise conflict("该资质已有待审申请", "application_pending")
    if has_certification(db, user.id, name):
        raise conflict("已持有该资质且在有效期内", "certification_exists")

    row = CertificationApplication(
        user_id=user.id, name=name, holder_name=holder_name,
        cert_number=cert_number, issuer=issuer, expires_at=expires_at, images=images,
    )
    db.add(row)
    db.flush()
    _mark_images_sensitive(db, images, user.id)
    return row


def _mark_images_sensitive(db: Session, names: list[str], owner_id: int) -> None:
    """CERT-010 证件影像是**敏感个人信息**，标记后 `/files/{name}` 一律拒绝匿名读。

    这条不是资质模块的洁癖：`/files/{name}` 是匿名能力 URL，设计前提是
    「名字不可猜」。对任务配图那个权衡是对的，对身份证/电工证不是——
    一个匿名可读的 URL 一旦出现在日志、浏览器历史或转发的截图里，
    就等于把证件交出去了。
    """
    from app.modules.files.models import UploadedFile

    for name in names:
        row = db.get(UploadedFile, name)
        if row and row.owner_id == owner_id:
            row.sensitive = True
            db.add(row)


def decide(db: Session, app_row: CertificationApplication, admin: User,
           approve: bool, reason: str) -> CertificationApplication:
    """CERT-004 人工审核。通过才写入用户资质。"""
    if app_row.status != "pending":
        raise conflict("该申请已处理", "already_decided")
    if not approve and not reason.strip():
        raise bad_request("驳回必须写明原因，否则申请人不知道该补什么",
                          "reason_required")
    app_row.status = "approved" if approve else "rejected"
    app_row.decision_reason = reason
    app_row.decided_by = admin.id
    app_row.decided_at = utcnow()
    db.add(app_row)
    # session 是 autoflush=False 的，不 flush 的话下面 active_certifications()
    # 的查询看不到刚改的 status，快照会算成空——这条被测试抓到过。
    db.flush()

    user = db.get(User, app_row.user_id)
    if user:
        # `user.certifications` 保留为「展示用快照」，准入判断不读它（读 active_certifications）。
        # 两处不一致时以申请表为准——快照漂了不会放行任何人。
        user.certifications = active_certifications(db, user.id)
        db.add(user)
    return app_row


def revoke(db: Session, app_row: CertificationApplication, admin: User,
           reason: str) -> CertificationApplication:
    if app_row.status != "approved":
        raise conflict("仅已核准的资质可撤销", "not_approved")
    app_row.status = "revoked"
    app_row.decision_reason = reason
    app_row.decided_by = admin.id
    app_row.decided_at = utcnow()
    db.add(app_row)
    db.flush()          # 同上：撤销后快照必须立刻不含它
    user = db.get(User, app_row.user_id)
    if user:
        user.certifications = active_certifications(db, user.id)
        db.add(user)
    return app_row


def expiring_soon(db: Session, days: int = 30) -> list[CertificationApplication]:
    from datetime import timedelta

    limit = utcnow() + timedelta(days=days)
    return (
        db.query(CertificationApplication)
        .filter(CertificationApplication.status == "approved",
                CertificationApplication.expires_at.isnot(None),
                CertificationApplication.expires_at <= limit,
                CertificationApplication.expires_at > utcnow())
        .all()
    )
