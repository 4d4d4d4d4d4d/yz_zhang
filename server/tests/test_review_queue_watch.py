"""QUEUE-010/011/012 / CS-031 / PAY-045 没有人盯的队列（78 号 spec）。

V101 给六个人审队列装了出口，V102 给三个装了入口。探针问第三个问题——
**东西进来了、出口也有了，谁会去看？**

    PROBE SUPPORT_SLA_HOURS = 24（全仓只有定义，没有任何使用）
    PROBE 管理员通知条数：跑 job 前 0 条，跑完 0 条
    PROBE 提单人收到的通知：[]
    PROBE 工单/资质/团队/图片 四个队列 30 天前的东西全都还在

顺手问「队列长了怎么办」：五个队列都**接受 `offset` 然后忽略它**——
翻页的人看到第一页无限重复，而且不知道自己在原地。
"""
from datetime import timedelta

from app.core.config import settings
from app.core.db import SessionLocal
from app.modules.account.models import utcnow
from app.modules.admin.queues import QUEUES
from tests.conftest import JOB_HEADERS, auth, make_admin, register, topup, verify_user


def _notes(client, user, title=None):
    rows = client.get("/api/v1/notifications?limit=100", headers=auth(user)).json()
    items = rows["items"] if isinstance(rows, dict) else rows
    return [n for n in items if title is None or n["title"] == title]


def _open_ticket(client, phone: str, subject="提现没到账"):
    u = register(client, phone, "提问的人")
    tid = client.post("/api/v1/support/tickets",
                      json={"subject": subject, "body": "急"},
                      headers=auth(u)).json()["id"]
    return u, tid


def _age_ticket(tid: int, hours: float):
    with SessionLocal() as db:
        from app.modules.support.models import Ticket

        db.get(Ticket, tid).created_at = utcnow() - timedelta(hours=hours)
        db.commit()


# ------------------------------------------------- QUEUE-010 声明表
def test_queue010_every_declared_queue_is_visible_in_the_overview(client):
    """声明表里的每个队列都要能在 `/admin/queues` 里查到。

    新增一个人审队列而不登记 → 它又会变成一个没人盯的队列。
    """
    admin = make_admin(client, "13800150009")
    body = client.get("/api/v1/admin/queues", headers=auth(admin)).json()
    keys = {q["key"] for q in body["queues"]}
    assert keys == {q.key for q in QUEUES}, "概览与声明表不一致"
    for row in body["queues"]:
        assert row["sla_hours"] > 0, f"{row['key']} 没有 SLA"
        assert row["label"], f"{row['key']} 没有中文名"


def test_queue010_not_telling_the_submitter_needs_a_reason_not_a_boolean():
    """「不告知提交方」必须写明理由。

    写成 `False` 的话，下一个人会顺手把它改成 `True`——
    而可疑活动复核那一行是 AML-030/031 的保密义务
    （V90 立下的做法：声明表的值是原因，不是开关）。
    """
    silent = [q for q in QUEUES if not q.tells_submitter]
    assert silent, "一条「不告知」都没有？断言写错了"
    for q in silent:
        assert len(q.no_tell_why) >= 15, f"{q.key} 不告知提交方却没写理由"
        assert "AML" in q.no_tell_why or "保密" in q.no_tell_why


def test_queue010_the_sla_setting_really_exists_in_config():
    """SLA 取的是**配置项的名字**，配置改了跟着变——不是抄一个数字下来。"""
    for q in QUEUES:
        assert hasattr(settings, q.sla_setting), f"{q.key} 引用了不存在的配置项"
        assert q.sla_hours() > 0


def test_cs031_tickets_use_the_support_sla_that_was_never_used(client):
    """`SUPPORT_SLA_HOURS` 此前全仓只有定义、没有任何使用。"""
    tickets = [q for q in QUEUES if q.key == "tickets"]
    assert tickets and tickets[0].sla_setting == "SUPPORT_SLA_HOURS"
    admin = make_admin(client, "13800150019")
    row = [q for q in client.get("/api/v1/admin/queues", headers=auth(admin)).json()["queues"]
           if q["key"] == "tickets"][0]
    assert row["sla_hours"] == settings.SUPPORT_SLA_HOURS


# ------------------------------------------------- QUEUE-011 汇总催办
def test_queue011_backlog_reaches_the_admins_as_one_digest(client):
    """一轮只发**一条**汇总：四条相似的通知会让运营把整类关掉。"""
    admin = make_admin(client, "13800150029")
    _u, tid = _open_ticket(client, "13800150020")
    _age_ticket(tid, settings.SUPPORT_SLA_HOURS + 5)

    r = client.post("/api/v1/admin/jobs/remind-review-queues", headers=JOB_HEADERS)
    assert r.status_code == 200, r.text
    assert "tickets" in r.json()["breached"]

    digest = _notes(client, admin, "人审队列积压")
    assert len(digest) == 1, "汇总应当只有一条"
    body = digest[0]["body"]
    assert "客服工单" in body and "1 件" in body
    # 数字取自配置（V61/V90：文案里的数字不许是字面量）
    assert f"SLA {settings.SUPPORT_SLA_HOURS} 小时" in body


def test_queue011_queues_within_sla_do_not_appear(client):
    """没超的队列不该出现在催办里——否则运营学会忽略它。"""
    admin = make_admin(client, "13800150039")
    _u, tid = _open_ticket(client, "13800150030")
    _age_ticket(tid, 1)      # 刚提的

    r = client.post("/api/v1/admin/jobs/remind-review-queues", headers=JOB_HEADERS)
    assert r.json()["breached"] == []
    assert not _notes(client, admin, "人审队列积压")


def test_queue011_overview_counts_what_is_waiting(client):
    admin = make_admin(client, "13800150049")
    _u, tid = _open_ticket(client, "13800150040")
    _age_ticket(tid, settings.SUPPORT_SLA_HOURS + 2)

    body = client.get("/api/v1/admin/queues", headers=auth(admin)).json()
    row = [q for q in body["queues"] if q["key"] == "tickets"][0]
    assert row["pending"] == 1
    assert row["oldest_wait_hours"] >= settings.SUPPORT_SLA_HOURS
    assert row["breached"] is True
    assert body["total_pending"] >= 1
    assert "tickets" in body["breached"]


def test_queue011_withdrawals_say_their_chasing_lives_elsewhere(client):
    """「这个队列有没有人盯」的答案可能是「有，在别处」——75 号那套。"""
    admin = make_admin(client, "13800150059")
    row = [q for q in client.get("/api/v1/admin/queues", headers=auth(admin)).json()["queues"]
           if q["key"] == "withdrawals"][0]
    assert "75" in row["chased_elsewhere"], "提现队列没说清催办在哪"


# ------------------------------------------------- QUEUE-012 等的人也被告知
def test_queue012_submitter_is_told_once_when_the_sla_is_breached(client):
    """沉默比慢更伤人：慢可以理解，沉默让人以为自己被忽略了。"""
    make_admin(client, "13800150069")
    u, tid = _open_ticket(client, "13800150060")
    _age_ticket(tid, settings.SUPPORT_SLA_HOURS + 3)

    r = client.post("/api/v1/admin/jobs/remind-review-queues", headers=JOB_HEADERS)
    assert r.json()["submitters_told"] == 1
    told = _notes(client, u, "你的申请仍在处理中")
    assert told, "超了 SLA 而提单人一个字也没收到"
    assert "客服工单" in told[0]["body"]
    assert str(settings.SUPPORT_SLA_HOURS) in told[0]["body"]

    # 再跑一轮不许重复告知——每小时一条比不发更糟
    r = client.post("/api/v1/admin/jobs/remind-review-queues", headers=JOB_HEADERS)
    assert r.json()["submitters_told"] == 0
    assert len(_notes(client, u, "你的申请仍在处理中")) == 1


def test_queue012_aml_subject_is_never_told(client):
    """可疑活动的当事人**不**被告知：AML-030/031 的保密义务。

    告诉他「你被标记了、正在复核」等于教他下次怎么规避。
    """
    admin = make_admin(client, "13800150079")
    u = register(client, "13800150070", "被标记的人")
    verify_user(client, u, name="被标记")
    with SessionLocal() as db:
        from app.modules.aml.models import SuspiciousActivity

        db.add(SuspiciousActivity(user_id=u["id"], pattern="fast_in_out",
                                  detail="快进快出", amount_cents=100000,
                                  status="pending",
                                  created_at=utcnow() - timedelta(days=30)))
        db.commit()

    r = client.post("/api/v1/admin/jobs/remind-review-queues", headers=JOB_HEADERS)
    assert "aml" in r.json()["breached"], "积压了却没进汇总"
    # 合规官看得到；当事人一个字也收不到
    assert _notes(client, admin, "人审队列积压"), "合规官没被催"
    assert not _notes(client, u, "你的申请仍在处理中"), "告诉当事人他被标记了"


def test_queue012_team_owner_is_the_one_told(client):
    """团队本身是一行 User，而收通知的得是人（owner）。"""
    make_admin(client, "13800150089")
    owner = register(client, "13800150080", "老板")
    verify_user(client, owner, name="老板")
    tid = client.post("/api/v1/teams", json={"name": "等核验的队"},
                      headers=auth(owner)).json()["id"]
    client.post(f"/api/v1/teams/{tid}/company",
                json={"company_name": "某某科技有限公司", "tax_number": "91310000X",
                      "license_images": ["lic.png"]}, headers=auth(owner))
    with SessionLocal() as db:
        from app.modules.team.models import Team

        db.get(Team, tid).created_at = utcnow() - timedelta(hours=settings.REVIEW_SLA_HOURS + 5)
        db.commit()

    client.post("/api/v1/admin/jobs/remind-review-queues", headers=JOB_HEADERS)
    assert _notes(client, owner, "你的申请仍在处理中"), "owner 没收到告知"


# ------------------------------------------------- PAY-045 分页真的生效
def test_pay045_offset_actually_skips_on_every_queue(client):
    """**接受一个参数然后忽略它**，比拒绝它更糟：翻页的人以为自己在翻。"""
    admin = make_admin(client, "13800150099")
    ids = []
    for i in range(3):
        _u, tid = _open_ticket(client, f"1380015010{i}", subject=f"问题{i}")
        ids.append(tid)

    first = client.get("/api/v1/admin/tickets?limit=1&offset=0", headers=auth(admin)).json()
    second = client.get("/api/v1/admin/tickets?limit=1&offset=1", headers=auth(admin)).json()
    assert len(first) == 1 and len(second) == 1
    assert first[0]["id"] != second[0]["id"], "offset 被忽略了"


def test_pay045_withdraw_queue_pages_too(client):
    """第 201 笔在界面上「不存在」——而那是一笔冻着的钱。"""
    admin = make_admin(client, "13800150199")
    rids = []
    for i in range(2):
        phone = f"1380015020{i}"
        u = register(client, phone, "提现的人")
        verify_user(client, u, name="提现")
        topup(client, u, settings.LARGE_WITHDRAW_CENTS + 200000)
        client.put("/api/v1/wallet/payout-account",
                   json={"kind": "bank", "account_no": f"6222{phone[-8:]}", "holder_name": "提现"},
                   headers=auth(u))
        rids.append(client.post("/api/v1/wallet/withdraw",
                                json={"amount_cents": settings.LARGE_WITHDRAW_CENTS + 1000},
                                headers=auth(u)).json()["request_id"])

    first = client.get("/api/v1/wallet/withdraw-requests?status=pending&limit=1&offset=0",
                       headers=auth(admin)).json()
    second = client.get("/api/v1/wallet/withdraw-requests?status=pending&limit=1&offset=1",
                        headers=auth(admin)).json()
    assert first and second and first[0]["id"] != second[0]["id"], "提现队列的 offset 没生效"


def test_pay045_other_queues_accept_offset(client):
    """资质 / 团队 / 图片三个队列同样要真的翻页。"""
    admin = make_admin(client, "13800150299")
    for i in range(3):
        u = register(client, f"1380015030{i}", "持证人")
        verify_user(client, u, name=f"张{i}")
        client.post("/api/v1/users/me/certifications",
                    json={"name": f"证{i}", "holder_name": f"张{i}",
                          "cert_number": f"C30{i}", "images": ["c.png"]}, headers=auth(u))

    a = client.get("/api/v1/admin/certifications/pending?limit=1&offset=0",
                   headers=auth(admin)).json()
    b = client.get("/api/v1/admin/certifications/pending?limit=1&offset=1",
                   headers=auth(admin)).json()
    assert a and b and a[0]["id"] != b[0]["id"], "资质队列的 offset 没生效"
