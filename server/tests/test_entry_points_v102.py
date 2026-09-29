"""ACC-041 / CERT-033 / NTF-065 / CS-032 / TAX-024 五条闭环的入口（77 号 spec）。

这五条的服务端一直都在，SDK 也一直都在，**端上没有人调**：

    resetPassword / smsLogin / sendSmsCode    sdk=True web=False app=False
    submitCertification                       sdk=True web=False app=False
    createTicket / myTickets                  sdk=True web=False app=False
    requestInvoice                            sdk=True web=False app=False
    notificationPrefs / setNotificationPref   sdk=True web=False app=False

「有能力」和「有人用得上」是两件事。这一篇钉住服务端那半边的行为，
端上那半边由 `test_sdk_method_triage.py` 与 web 测试钉住。
"""
from app.core.db import SessionLocal
from tests.conftest import auth, make_admin, register, topup, verify_user
from tests.test_task_flow import match_and_fund, publish_task


def _code(client, phone: str, scene: str) -> str:
    """沙箱短信通道回显验证码（19/27 号 spec 的既有约定）。"""
    r = client.post("/api/v1/auth/send-code", json={"phone": phone, "scene": scene})
    assert r.status_code == 200, r.text
    code = r.json().get("dev_code")
    assert code, "沙箱通道没有回显验证码，找回密码这条线就测不了"
    return code


# ------------------------------------------------- ACC-041 忘了密码还能进来
def test_acc041_forgotten_password_can_be_reset_and_used(client):
    """忘了密码的人此前**进不来**：改密码的入口在登录之后。"""
    u = register(client, "13800130001", "忘密码的人")
    code = _code(client, "13800130001", "reset")

    r = client.post("/api/v1/auth/reset-password",
                    json={"phone": "13800130001", "sms_code": code,
                          "new_password": "newpass12345"})
    assert r.status_code == 200, r.text

    # 新密码能登录
    r = client.post("/api/v1/auth/login",
                    json={"phone": "13800130001", "password": "newpass12345"})
    assert r.status_code == 200, r.text
    # 旧会话被吊销（ACC-004 的既有行为，这里一并钉住）。
    # 吊销后既有实现回 403（不是 401）——按**实际契约**断言，
    # 不按我以为的那个
    assert client.get("/api/v1/users/me", headers=auth(u)).status_code == 403


def test_acc041_sms_login_needs_no_password(client):
    """验证码登录：密码想不起来、也不想改的时候的那条路。"""
    register(client, "13800130010", "验证码登录的人")
    code = _code(client, "13800130010", "login")
    r = client.post("/api/v1/auth/login-sms",
                    json={"phone": "13800130010", "sms_code": code})
    assert r.status_code == 200, r.text
    assert r.json()["token"]


def test_acc041_reset_needs_a_real_code(client):
    """随便编一个验证码不能改别人的密码。"""
    register(client, "13800130020", "别人")
    r = client.post("/api/v1/auth/reset-password",
                    json={"phone": "13800130020", "sms_code": "000000",
                          "new_password": "hacked12345"})
    assert r.status_code == 400, r.text


# ------------------------------------------------- CERT-033 资质交得上去
def test_cert033_submitted_application_shows_up_in_the_admin_queue(client):
    """V101 的核验台此前会一直是空的——**没有任何端能提交一份资质申请**。"""
    user = register(client, "13800130030", "持证人")
    verify_user(client, user, name="张三")
    r = client.post("/api/v1/users/me/certifications",
                    json={"name": "电工证", "holder_name": "张三",
                          "cert_number": "C130030", "issuer": "某市人社局",
                          "images": ["cert-130030.png"]},
                    headers=auth(user))
    assert r.status_code == 201, r.text

    mine = client.get("/api/v1/users/me/certifications", headers=auth(user)).json()
    assert mine["applications"], "自己的申请列表里看不到刚提交的那份"
    assert mine["applications"][0]["status"] == "pending"

    admin = make_admin(client, "13800130039")
    queue = client.get("/api/v1/admin/certifications/pending", headers=auth(admin)).json()
    assert [q for q in queue if q["user_id"] == user["id"]], "提交了却没进核验队列"


def test_cert033_rejection_reason_comes_back_to_the_applicant(client):
    """驳回理由要能被申请人读到——写了看不见，那条强制只是给运营加了道手续。"""
    user = register(client, "13800130040", "持证人")
    verify_user(client, user, name="张三")
    client.post("/api/v1/users/me/certifications",
                json={"name": "电工证", "holder_name": "张三",
                      "cert_number": "C130040", "images": ["c.png"]},
                headers=auth(user))
    admin = make_admin(client, "13800130049")
    app_id = client.get("/api/v1/admin/certifications/pending",
                        headers=auth(admin)).json()[0]["id"]
    client.post(f"/api/v1/admin/certifications/{app_id}/decide",
                json={"approve": False, "reason": "证件影像不清晰，请重新上传"},
                headers=auth(admin))

    mine = client.get("/api/v1/users/me/certifications", headers=auth(user)).json()
    row = [a for a in mine["applications"] if a["id"] == app_id][0]
    assert row["status"] == "rejected"
    assert "不清晰" in row["decision_reason"], "驳回理由回不到申请人面前"


# ------------------------------------------------- NTF-065 开关与「关不掉的」
def test_ntf065_prefs_say_which_notices_cannot_be_switched_off(client):
    """界面要说清哪些关不掉，而那份清单**必须来自服务端**。

    `MUST_REACH` 是一张会变的表（V65 立、V100 加过一行）：
    界面里抄一份，它第二天就过期了。
    """
    from app.modules.notification.service import MUST_REACH

    u = register(client, "13800130050", "调开关的人")
    r = client.get("/api/v1/notifications/prefs", headers=auth(u))
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body["prefs"]) == {"task", "system", "interaction"}
    assert "funds" in body["always_on_categories"]
    # 服务端的必达表逐条返回，而且带上「为什么」
    titles = {(a["category"], a["title"]) for a in body["always_on"]}
    assert titles == set(MUST_REACH), "返回的必达清单与服务端的表不一致"
    assert all(a["why"] for a in body["always_on"]), "没说为什么关不掉"


def test_ntf065_switch_works_and_funds_cannot_be_turned_off(client):
    u = register(client, "13800130060", "调开关的人")
    r = client.put("/api/v1/notifications/prefs?category=system&enabled=false",
                   headers=auth(u))
    assert r.status_code == 200, r.text
    assert client.get("/api/v1/notifications/prefs",
                      headers=auth(u)).json()["prefs"]["system"] is False

    r = client.put("/api/v1/notifications/prefs?category=funds&enabled=false",
                   headers=auth(u))
    assert r.status_code == 400, r.text
    assert r.json()["detail"]["code"] == "funds_mandatory"


# ------------------------------------------------- CS-032 工单自助
def test_cs032_user_can_open_a_ticket_and_read_the_reply(client):
    """此前工单只有 FAQ 机器人升级时会自动生成；运营认真回了，而提问的人
    只收到一条通知，回到平台上无处可看。"""
    u = register(client, "13800130070", "提问的人")
    r = client.post("/api/v1/support/tickets",
                    json={"subject": "提现没到账", "body": "昨天提的现在还没到"},
                    headers=auth(u))
    assert r.status_code == 201, r.text
    # SDK 声明里有 reply（一开始是空串），此前服务端不返回——「声明了却不给」
    assert "reply" in r.json()
    tid = r.json()["id"]

    rows = client.get("/api/v1/support/tickets", headers=auth(u)).json()
    row = [t for t in rows if t["id"] == tid][0]
    # 列表里要有正文：少了它，用户看到的是一排标题、点进去没有内容
    assert row["body"] == "昨天提的现在还没到"

    admin = make_admin(client, "13800130079")
    client.post(f"/api/v1/admin/tickets/{tid}/resolve",
                json={"reply": "已核查，银行处理中"}, headers=auth(admin))
    rows = client.get("/api/v1/support/tickets", headers=auth(u)).json()
    assert [t for t in rows if t["id"] == tid][0]["reply"] == "已核查，银行处理中", \
        "运营回了，而提问的人在平台上看不到"


# ------------------------------------------------- TAX-024 发票
def test_tax024_requester_can_ask_for_the_platform_fee_invoice(client, requester):
    """V101 让团队企业信息终于核得过了，而开票的入口不存在。"""
    worker = register(client, "13800130080", "执行者")
    verify_user(client, worker, name="执行")
    topup(client, requester, 200000)
    task = publish_task(client, requester)
    match_and_fund(client, requester, worker, task)
    client.post(f"/api/v1/tasks/{task['id']}/deliver", headers=auth(worker))
    client.post(f"/api/v1/tasks/{task['id']}/accept-delivery", headers=auth(requester))

    with SessionLocal() as db:
        from app.modules.contract.models import Contract

        cid = db.query(Contract).filter(Contract.task_id == task["id"]).first().id

    r = client.post("/api/v1/finance/invoices",
                    json={"contract_id": cid, "title": "某某科技有限公司", "tax_no": "91310000X"},
                    headers=auth(requester))
    assert r.status_code == 201, r.text
    body = r.json()
    # 口径由服务端给，界面原样显示：只开平台服务费那部分
    assert "平台服务费" in body["scope_note"]
    assert body["amount_cents"] > 0

    rows = client.get("/api/v1/finance/invoices", headers=auth(requester)).json()
    assert rows and rows[0]["contract_id"] == cid
    # SDK 声明过 created_at，服务端给的是 at（V102 已把声明改对）
    assert "at" in rows[0]


def test_tax024_unsettled_contract_cannot_be_invoiced(client, requester):
    """没放款就没有服务费可开——含糊其辞地开票是虚开，不是服务。"""
    worker = register(client, "13800130090", "执行者")
    verify_user(client, worker, name="执行")
    topup(client, requester, 200000)
    task = publish_task(client, requester)
    match_and_fund(client, requester, worker, task)
    with SessionLocal() as db:
        from app.modules.contract.models import Contract

        cid = db.query(Contract).filter(Contract.task_id == task["id"]).first().id

    r = client.post("/api/v1/finance/invoices",
                    json={"contract_id": cid, "title": "某某科技有限公司"},
                    headers=auth(requester))
    assert r.status_code == 400, r.text
    assert r.json()["detail"]["code"] == "not_settled"
