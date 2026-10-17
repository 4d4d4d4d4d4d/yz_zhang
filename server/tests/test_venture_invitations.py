"""COOP-060 合作体邀请的另一半（142 号 spec）。

邀请制早就有了（COOP-021：没有公开加入端点），但被邀请的人只收到一条通知文字，
**没有任何接口能列出「我收到的邀请」**，也不能拒绝——两端都没法做「接受邀请」的界面。
"""
from datetime import timedelta

from app.core.db import SessionLocal
from app.modules.account.models import utcnow
from app.modules.coop.models import VentureInvitation
from tests.conftest import auth
from tests.test_early_cooperation import VER, make_user, make_venture

API = "/api/v1/ventures"


def test_invitee_lists_pending_invitations_with_who_and_what(client):
    founder = make_user(client, "13800220001", "阿青")
    guest = make_user(client, "13800220002", "小林")
    vid = make_venture(client, founder, name="社区咖啡")
    assert client.post(f"{API}/{vid}/invitations", json={"user_id": guest["id"]}, headers=auth(founder)).status_code == 201
    rows = client.get(f"{API}/invitations", headers=auth(guest)).json()
    assert [(r["venture_id"], r["name"], r["inviter_nickname"], r["risk_disclosure_version"]) for r in rows] == \
        [(vid, "社区咖啡", "阿青", VER)]
    assert client.get(f"{API}/invitations", headers=auth(founder)).json() == [], "只列发给我的"
    # 接受后就不再是待处理
    assert client.post(f"{API}/{vid}/members", json={"risk_disclosure_version": VER}, headers=auth(guest)).status_code == 201
    assert client.get(f"{API}/invitations", headers=auth(guest)).json() == []


def test_expired_invitations_are_not_listed(client):
    founder = make_user(client, "13800220003", "发起人")
    guest = make_user(client, "13800220004", "客人")
    vid = make_venture(client, founder)
    client.post(f"{API}/{vid}/invitations", json={"user_id": guest["id"]}, headers=auth(founder))
    with SessionLocal() as db:
        inv = db.query(VentureInvitation).filter_by(invitee_id=guest["id"]).one()
        inv.expires_at = utcnow() - timedelta(minutes=1)
        db.commit()
    assert client.get(f"{API}/invitations", headers=auth(guest)).json() == []


def test_decline_only_my_pending_invitation_and_then_join_is_refused(client):
    founder = make_user(client, "13800220005", "发起人")
    guest = make_user(client, "13800220006", "客人")
    other = make_user(client, "13800220007", "路人")
    vid = make_venture(client, founder)
    client.post(f"{API}/{vid}/invitations", json={"user_id": guest["id"]}, headers=auth(founder))
    r = client.post(f"{API}/{vid}/invitations/decline", headers=auth(other))
    assert r.status_code == 404 and r.json()["detail"]["code"] == "invitation_not_found", "不能替别人拒绝"
    assert client.post(f"{API}/{vid}/invitations/decline", headers=auth(guest)).json()["status"] == "declined"
    assert client.post(f"{API}/{vid}/invitations/decline", headers=auth(guest)).status_code == 404, "拒绝过的不能再拒"
    join = client.post(f"{API}/{vid}/members", json={"risk_disclosure_version": VER}, headers=auth(guest))
    assert join.status_code == 403 and join.json()["detail"]["code"] == "invitation_required", "拒绝之后不能再凭这张邀请加入"
    # 重新邀请可以
    client.post(f"{API}/{vid}/invitations", json={"user_id": guest["id"]}, headers=auth(founder))
    assert len(client.get(f"{API}/invitations", headers=auth(guest)).json()) == 1


def test_shape(client):
    from tests.test_client_shape_alignment import _assert_shape

    founder = make_user(client, "13800220008", "发起人")
    guest = make_user(client, "13800220009", "客人")
    vid = make_venture(client, founder)
    client.post(f"{API}/{vid}/invitations", json={"user_id": guest["id"]}, headers=auth(founder))
    rows = client.get(f"{API}/invitations", headers=auth(guest)).json()
    first = rows[0]
    _assert_shape(first, "VentureInvitationView")
