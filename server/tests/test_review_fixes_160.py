"""功能检视发现的两处缺口（160 号 spec）。

CORS-001：网页与 API 不同源部署时，浏览器只让脚本读到 `Access-Control-Expose-Headers` 列出的响应头；
不列，后台分页的总条数、开放 API 的剩余次数在浏览器里都是 null。
ESCA-055：客服工单（标题、内容、往来）既不在数据导出里，注销时也没处置。
"""
from app.core.config import settings
from app.core.db import SessionLocal
from app.modules.account.deletion import erase_personal_data
from app.modules.account.models import User
from app.modules.analytics.models import AnalyticsEvent
from app.modules.support.models import Ticket, TicketReply
from tests.conftest import auth, make_admin

API = "/api/v1"


def test_cors_exposes_the_headers_clients_read(client, monkeypatch):
    from app.main import EXPOSED_HEADERS

    origin = (settings.cors_origins() or ["http://localhost:5173"])[0]
    r = client.get("/healthz", headers={"Origin": origin})
    exposed = {h.strip().lower() for h in r.headers.get("access-control-expose-headers", "").split(",") if h.strip()}
    for h in ("X-Total-Count", "Retry-After", "X-RateLimit-Remaining", "X-Quota-Remaining", "X-Account-Quota-Remaining"):
        assert h in EXPOSED_HEADERS and h.lower() in exposed, h


def test_tickets_are_in_my_export_and_scrubbed_on_erase(client, requester):
    s1 = make_admin(client, "13800330001", "客服")
    tid = client.post(f"{API}/support/tickets", json={"subject": "我家住址被别人看到了", "body": "地址是某某路 3 号"},
                      headers=auth(requester)).json()["id"]
    client.post(f"{API}/admin/tickets/{tid}/reply", json={"reply": "已帮你隐藏地址"}, headers=auth(s1))
    client.post(f"{API}/legal/ask", json={"question": "房东不退押金怎么办"}, headers=auth(requester))
    out = client.get(f"{API}/users/me/export", headers=auth(requester)).json()
    t = out["tickets"][0]
    assert t["subject"] == "我家住址被别人看到了" and t["body"] == "地址是某某路 3 号"
    assert t["replies"] == [{"body": "已帮你隐藏地址", "from": "客服", "created_at": t["replies"][0]["created_at"]}]
    with SessionLocal() as db:
        erase_personal_data(db, db.get(User, requester["id"]))
        db.commit()
        row = db.get(Ticket, tid)
        assert "住址" not in row.subject and row.body == "" and row.reply == ""
        assert all(r.body == "" for r in db.query(TicketReply).filter(TicketReply.ticket_id == tid))
        assert db.query(AnalyticsEvent).filter(AnalyticsEvent.user_id == requester["id"]).count() == 0
        assert db.query(AnalyticsEvent).filter(AnalyticsEvent.name == "legal_unanswered").count() == 1, "聚合数还在"


def test_tickets_escalated_to_a_dispute_are_kept(client, requester):
    tid = client.post(f"{API}/support/tickets", json={"subject": "对方不验收", "body": "交付了三次"},
                      headers=auth(requester)).json()["id"]
    with SessionLocal() as db:
        db.get(Ticket, tid).escalated_to_dispute_id = 99
        db.commit()
        erase_personal_data(db, db.get(User, requester["id"]))
        db.commit()
        assert db.get(Ticket, tid).body == "交付了三次", "转成纠纷的工单按纠纷材料留存"
