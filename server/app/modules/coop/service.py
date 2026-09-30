"""COOP 份额计算、贡献确认与收益分配（50 号 spec）。"""
from sqlalchemy.orm import Session

from app.core.errors import bad_request, conflict, forbidden
from app.modules.account.models import User, utcnow
from app.modules.wallet import service as wallet

from . import compliance_path as cpath
from .models import Contribution, Distribution, Venture, VentureMember


def get_venture(db: Session, venture_id: int) -> Venture | None:
    return db.get(Venture, venture_id)


def members(db: Session, venture_id: int) -> list[VentureMember]:
    return (
        db.query(VentureMember)
        .filter(VentureMember.venture_id == venture_id, VentureMember.active.is_(True))
        .order_by(VentureMember.id)
        .all()
    )


def is_member(db: Session, venture_id: int, user_id: int) -> bool:
    return any(m.user_id == user_id for m in members(db, venture_id))


def accepted_contributions(db: Session, venture_id: int) -> list[Contribution]:
    return (
        db.query(Contribution)
        .filter(Contribution.venture_id == venture_id, Contribution.status == "accepted")
        .all()
    )


def shares_bps(db: Session, venture_id: int) -> list[dict]:
    """COOP-011 份额 = 已确认贡献的函数，**每次现算**。

    不存成字段是有意的：存下来就会漂——有人新增贡献而没人回来重算，
    份额就是错的，而且不会有任何东西报错。这是这个项目里反复出现的
    「写错了不会出错的声明」，这次从一开始就不给它机会。

    COOP-012 合计恒为 10000 bps：余数给到贡献最多的那个人，
    **不四舍五入到各自身上**——那样合计会差几个基点，分配时就少分或多分。
    """
    rows = accepted_contributions(db, venture_id)
    total = sum(c.valued_cents for c in rows)
    per_user: dict[int, int] = {}
    for c in rows:
        per_user[c.user_id] = per_user.get(c.user_id, 0) + c.valued_cents
    if total <= 0:
        return [{"user_id": m.user_id, "valued_cents": 0, "share_bps": 0}
                for m in members(db, venture_id)]

    out = []
    allocated = 0
    ordered = sorted(per_user.items(), key=lambda kv: (-kv[1], kv[0]))
    for i, (uid, valued) in enumerate(ordered):
        if i == len(ordered) - 1:
            bps = 10000 - allocated          # 余数归最后一个，保证合计精确
        else:
            bps = valued * 10000 // total
            allocated += bps
        out.append({"user_id": uid, "valued_cents": valued, "share_bps": bps})
    return out


def join_block(db: Session, venture: Venture, user: User, risk_version: str) -> str:
    """能不能加入；空串表示可以。单一判断来源。"""
    if venture.status == "closed":
        return "该合作体已关闭"
    if user.is_agent or user.is_venture:
        return "AI 助理与合作体账号不能作为成员加入"
    if not user.is_verified:
        return "需先完成实名认证"
    if is_member(db, venture.user_id, user.id):
        return "已是该合作体成员"
    # COOP-030 不签风险揭示书不能加入。
    # 一个不告诉人有风险就拉人进来的早期合作，本身就是纠纷的起点。
    if risk_version != cpath.RISK_DISCLOSURE_VERSION:
        return "需先签署当前版本的风险揭示书"
    return ""


def add_member(db: Session, venture: Venture, user: User, risk_version: str,
               role: str = "member") -> VentureMember:
    block = join_block(db, venture, user, risk_version)
    if block:
        raise bad_request(block, "join_blocked")
    row = VentureMember(
        venture_id=venture.user_id, user_id=user.id, role=role,
        risk_disclosure_version=risk_version, risk_accepted_at=utcnow(),
    )
    db.add(row)
    db.flush()
    return row


def confirm_contribution(db: Session, contribution: Contribution, confirmer: User,
                         valued_cents: int, note: str, accept: bool) -> Contribution:
    """COOP-010 确认贡献。**确认人不能是贡献人自己。**

    自报贡献等于自己发股份。这条写在代码里，不靠自觉。
    """
    if contribution.status != "proposed":
        raise conflict("该贡献已处理", "already_decided")
    if contribution.user_id == confirmer.id:
        raise forbidden("不能确认自己提交的贡献", "self_confirmation")
    if not is_member(db, contribution.venture_id, confirmer.id):
        raise forbidden("仅合作体成员可确认贡献")
    if accept and valued_cents <= 0:
        raise bad_request("确认贡献时必须给出计价", "valuation_required")

    contribution.status = "accepted" if accept else "rejected"
    contribution.valued_cents = valued_cents if accept else 0
    contribution.confirmed_by = confirmer.id
    contribution.confirm_note = note
    contribution.confirmed_at = utcnow()
    db.add(contribution)

    if accept:
        _anchor(db, "coop.contribution.accepted", contribution.venture_id, {
            "venture_id": contribution.venture_id,
            "contribution_id": contribution.id,
            "user_id": contribution.user_id,
            "valued_cents": valued_cents,
            "confirmed_by": confirmer.id,
        })
    return contribution


def distribute(db: Session, venture: Venture, operator: User, amount_cents: int,
               memo: str) -> Distribution:
    """COOP-020 分配。**钱只能来自合作体钱包的可用余额**——也就是真的收到了的钱。

    没有「预期收益」这个概念，代码里也不存在这个字段。这不是法务加的限制，
    是让这个模型落在合作内部分配而非涉众性金融的设计本身。
    """
    if amount_cents <= 0:
        raise bad_request("分配金额必须为正", "invalid_amount")
    acct = wallet.get_or_create(db, venture.user_id)
    if acct.available_cents < amount_cents:
        raise bad_request(
            f"合作体可用资金不足（当前 ¥{acct.available_cents / 100:.2f}）。"
            f"只能分配**已经实际收到**的收入。",
            "insufficient_venture_funds",
        )
    snapshot = [s for s in shares_bps(db, venture.user_id) if s["share_bps"] > 0]
    if not snapshot:
        raise conflict("尚无已确认贡献，无法计算分配比例", "no_shares")

    dist = Distribution(
        venture_id=venture.user_id, total_cents=amount_cents,
        share_snapshot=snapshot, memo=memo, created_by=operator.id,
    )
    db.add(dist)
    db.flush()

    # 按快照分钱。**余数给最后一个**，与份额计算同一条规则——
    # 各自取整会让分出去的总额少几分，账就不平了。
    paid = 0
    for i, s in enumerate(snapshot):
        if i == len(snapshot) - 1:
            part = amount_cents - paid
        else:
            part = amount_cents * s["share_bps"] // 10000
            paid += part
        if part <= 0:
            continue
        wallet.transfer(db, venture.user_id, s["user_id"], part, None,
                        memo=f"合作体分配 #{dist.id}", kind="coop_distribution")

    _anchor(db, "coop.distribution", venture.user_id, {
        "venture_id": venture.user_id, "distribution_id": dist.id,
        "total_cents": amount_cents, "snapshot": snapshot,
    })
    return dist


def _anchor(db: Session, event_type: str, ref_id: int, payload: dict) -> None:
    """COOP-060 入存证哈希链。

    需求说「可追溯（有智能合约）」。可追溯的真实含义不是「有一张表存着」，
    而是**改一条历史记录必须重写整条后继链才不被发现**。
    """
    from app.modules.anchor import service as anchor

    anchor.anchor(db, event_type, "venture", ref_id, payload)


def compliance_for(db: Session, venture: Venture) -> dict:
    """COOP-040 按合作体的客观属性生成合规路径。**不阻断任何操作。**"""
    from app.modules.task.service import get_category

    dists = db.query(Distribution).filter(Distribution.venture_id == venture.user_id).all()
    acct = wallet.get_or_create(db, venture.user_id)
    required_cert = ""
    if venture.category:
        cat = get_category(db, venture.category)
        required_cert = cat.required_cert if cat else ""
    path = cpath.evaluate(
        member_count=len(members(db, venture.user_id)),
        has_funds=acct.available_cents > 0,
        distributed_total_cents=sum(d.total_cents for d in dists),
        distribution_count=len(dists),
        category_required_cert=required_cert,
    )
    return path.as_dict()
