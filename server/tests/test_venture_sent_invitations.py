"""COOP-062 邀请人看「我发出的邀请」及其状态（220 号 spec，V248）。

142 号 spec 让被邀请的人看得到、接得了、拒得掉邀请；发出邀请的那一侧却什么都看不到：对方接没接、拒没拒、过没过期。
"""
from datetime import timedelta

from app.core.db import SessionLocal
from app.modules.account.models import utcnow
from app.modules.coop.models import VentureInvitation
from tests.conftest import auth
from tests.test_early_cooperation import VER, make_user, make_venture

API = "/api/v1/ventures"


def test_inviter_sees_each_status_and_only_their_own(client):
    founder = make_user(client, "13900062000", "阿青")
    vid = make_venture(client, founder, name="社区咖啡")
    a, b, c, d = (make_user(client, f"1390006200{i}", n) for i, n in enumerate(["甲", "乙", "丙", "丁"], start=1))
    for u in (a, b, c, d):
        assert client.post(f"{API}/{vid}/invitations", json={"user_id": u["id"]}, headers=auth(founder)).status_code == 201
    client.post(f"{API}/{vid}/invitations/decline", headers=auth(b))
    client.post(f"{API}/{vid}/members", json={"risk_disclosure_version": VER}, headers=auth(d))
    with SessionLocal() as db:
        row = db.query(VentureInvitation).filter_by(venture_id=vid, invitee_id=c["id"]).one()
        row.expires_at = utcnow() - timedelta(minutes=1)
        db.commit()
    r = client.get(f"{API}/{vid}/invitations/sent", headers=auth(founder))
    assert r.status_code == 200, r.text
    got = {x["invitee_nickname"]: x["status"] for x in r.json()}
    assert got == {"甲": "pending", "乙": "declined", "丙": "expired", "丁": "accepted"}
    assert next(x for x in r.json() if x["invitee_nickname"] == "丁")["accepted_at"]
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(r.json()[0], "VentureSentInvitation")
    # 丁加入后自己也是成员：他没发过邀请，看到的是空表（只列本人发出的）
    assert client.get(f"{API}/{vid}/invitations/sent", headers=auth(d)).json() == []
    stranger = make_user(client, "13900062009", "外人")
    assert client.get(f"{API}/{vid}/invitations/sent", headers=auth(stranger)).status_code in (403, 404), "不是成员看不到"
