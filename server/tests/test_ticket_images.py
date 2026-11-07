"""ESCA-057 工单里追加图片（227 号 spec，V254）。

「提现页面报错」「订单显示异常」——用户以前只能用文字描述截图里的东西，客服再回一句「麻烦截个图」，
而工单里根本没有地方放图。现在提单与追加回复都能附最多 4 张自己上传过的图，客服后台看得到。
"""
from app.core.db import SessionLocal
from app.modules.files.models import UploadedFile
from tests.conftest import auth, register
from tests.test_ticket_assign_reply import _admin
from tests.test_uploads import upload

API = "/api/v1"


def _img(client, user):
    r = upload(client, user)
    assert r.status_code == 201, r.text
    return r.json()["url"]


def test_create_and_reply_with_screenshots_visible_to_user_and_staff(client):
    u = register(client, "13800327001", "提问的人")
    a, b = _img(client, u), _img(client, u)
    r = client.post(f"{API}/support/tickets", json={"subject": "提现页面报错", "body": "见截图", "images": [a, a]}, headers=auth(u))
    assert r.status_code == 201, r.text
    tid = r.json()["id"]
    r = client.post(f"{API}/support/tickets/{tid}/replies", json={"body": "又截了一张", "images": [b]}, headers=auth(u))
    assert r.status_code == 200, r.text
    mine = client.get(f"{API}/support/tickets", headers=auth(u)).json()[0]
    assert mine["images"] == [a], "同一张图只存一次"
    assert mine["replies"][-1]["images"] == [b]
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(mine, "MyTicket")
    agent = _admin(client, "13800327002", ["support"])
    d = client.get(f"{API}/admin/tickets/{tid}", headers=auth(agent)).json()
    assert d["images"] == [a] and d["thread"][-1]["images"] == [b]
    _assert_shape(d, "AdminTicketDetail")
    _assert_shape(d["thread"][-1], "AdminTicketThreadItem")
    # 图本身照常能读（能力 URL）
    assert client.get(a).status_code == 200


def test_only_own_non_sensitive_uploads_and_at_most_four(client):
    u = register(client, "13800327003", "提问的人")
    other = register(client, "13800327004", "别人")
    theirs = _img(client, other)
    url = f"{API}/support/tickets"
    r = client.post(url, json={"subject": "看看这张", "images": [theirs]}, headers=auth(u))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "ticket_image_not_yours"
    r = client.post(url, json={"subject": "外链", "images": ["https://evil.example/x.png"]}, headers=auth(u))
    assert r.json()["detail"]["code"] == "ticket_image_not_yours"
    mine = _img(client, u)
    with SessionLocal() as db:
        db.get(UploadedFile, mine.rsplit("/", 1)[-1]).sensitive = True
        db.commit()
    assert client.post(url, json={"subject": "证件", "images": [mine]}, headers=auth(u)).json()["detail"]["code"] == "ticket_image_not_yours"
    five = [_img(client, u) for _ in range(5)]
    r = client.post(url, json={"subject": "太多了", "images": five}, headers=auth(u))
    assert r.json()["detail"]["code"] == "ticket_too_many_images" and "最多附 4 张" in r.json()["detail"]["message"]
    tid = client.post(url, json={"subject": "正常"}, headers=auth(u)).json()["id"]
    r = client.post(f"{url}/{tid}/replies", json={"body": "补图", "images": five}, headers=auth(u))
    assert r.json()["detail"]["code"] == "ticket_too_many_images", "追加回复同样的限制"
    assert client.get(url, headers=auth(u)).json()[0]["replies"] == [], "被拒的那次什么都没留下"


def test_thanks_with_a_screenshot_still_reopens_and_deletion_clears_images(client):
    from datetime import timedelta

    from app.modules.account.models import utcnow
    from app.modules.support.models import Ticket, TicketReply

    u = register(client, "13800327005", "提问的人")
    img = _img(client, u)
    tid = client.post(f"{API}/support/tickets", json={"subject": "已解决的单", "images": [img]}, headers=auth(u)).json()["id"]
    with SessionLocal() as db:
        t = db.get(Ticket, tid)
        t.status, t.resolved_at = "resolved", utcnow() - timedelta(hours=1)
        db.commit()
    r = client.post(f"{API}/support/tickets/{tid}/replies", json={"body": "谢谢", "images": [img]}, headers=auth(u)).json()
    assert r["reopened"] is True and r["kept_closed"] is False, "带了截图就不是只说谢谢"
    exported = client.get(f"{API}/users/me/export", headers=auth(u)).json()["tickets"][0]
    assert exported["images"] and exported["replies"][-1]["images"]
    from app.modules.account.deletion import erase_personal_data
    from app.modules.account.models import User

    with SessionLocal() as db:
        erase_personal_data(db, db.get(User, u["id"]))
        db.commit()
    with SessionLocal() as db:
        assert not db.get(Ticket, tid).images, "注销后截图引用清掉（截图同样可能拍到个人情况）"
        assert all(not r.images for r in db.query(TicketReply).filter(TicketReply.ticket_id == tid))


# --------------------------------- ESCA-062 客服回复时附图（231 号 spec，V258）
def test_staff_reply_with_screenshots_reaches_the_user(client):
    u = register(client, "13800327011", "提问的人")
    tid = client.post(f"{API}/support/tickets", json={"subject": "在哪里改手机号"}, headers=auth(u)).json()["id"]
    agent = _admin(client, "13800327012", ["support"])
    shot = _img(client, agent)
    r = client.post(f"{API}/admin/tickets/{tid}/reply", json={"reply": "点右上角「设置」，见图", "images": [shot]}, headers=auth(agent))
    assert r.status_code == 200, r.text
    mine = client.get(f"{API}/support/tickets", headers=auth(u)).json()[0]
    assert mine["replies"][-1]["is_staff"] and mine["replies"][-1]["images"] == [shot]
    assert client.get(f"{API}/admin/tickets/{tid}", headers=auth(agent)).json()["thread"][-1]["images"] == [shot]
    assert any("（附 1 张图）" in t for t in [n for n in _bodies(u["id"])])
    # 客服也只能附自己上传的图；不带图时照旧
    others = _img(client, u)
    r = client.post(f"{API}/admin/tickets/{tid}/reply", json={"reply": "借用户的图", "images": [others]}, headers=auth(agent))
    assert r.json()["detail"]["code"] == "ticket_image_not_yours"
    r = client.post(f"{API}/admin/tickets/{tid}/reply", json={"reply": "好的"}, headers=auth(agent))
    assert r.status_code == 200
    assert client.get(f"{API}/support/tickets", headers=auth(u)).json()[0]["replies"][-1]["images"] == []


def _bodies(user_id):
    from app.modules.notification.models import Notification

    with SessionLocal() as db:
        return [n.body for n in db.query(Notification).filter(Notification.user_id == user_id)]
