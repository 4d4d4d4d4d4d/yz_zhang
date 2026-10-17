"""CERT 受限类目资质核验（51 号 spec）。

改造前 `POST /users/me/certifications` 是一行
`user.certifications += [name]`，注释写着「模拟审核即通过」——
**任何实名用户 POST 一个字符串就拿到「电工」资质**，
而受限类目的接单准入正是靠这个字段。

一个无证的人接了电工单，出事的是人身安全，赔的是平台的连带责任。
所以这些测试的核心不是「有没有审核页面」，而是
**在人工核过之前，那个类目一次都不放行**。
"""
import base64
from datetime import timedelta

from app.core.db import SessionLocal
from app.modules.account import cert_service
from app.modules.account.models import utcnow
from tests.conftest import auth, make_admin, register, topup, verify_user
from tests.test_task_flow import publish_task

PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x11" * 96).decode()


def upload_image(client, user):
    r = client.post("/api/v1/files",
                    json={"content_type": "image/png", "data_base64": PNG},
                    headers=auth(user))
    assert r.status_code == 201, r.text
    return r.json()["ref"]


def make_verified(client, phone, real_name="实名用户", nick="执行者"):
    u = register(client, phone, nick)
    verify_user(client, u, name=real_name)
    return u


def apply_cert(client, user, name="电工", holder="实名用户", images=None, **over):
    body = {
        "name": name, "holder_name": holder,
        "cert_number": "SH-12345678", "issuer": "上海市人社局",
        "expires_at": (utcnow() + timedelta(days=365)).isoformat(),
        "images": images if images is not None else [upload_image(client, user)],
        **over,
    }
    return client.post("/api/v1/users/me/certifications", json=body, headers=auth(user))


def apply_to_restricted_task(client, requester, worker):
    """去接一个受限类目（电工维修）的任务。"""
    task = publish_task(client, requester, category="电工维修", title="配电箱检修")
    return client.post(f"/api/v1/tasks/{task['id']}/applications",
                       json={"message": "我可以做"}, headers=auth(worker))


# ------------------------------------------------- CERT-001 提交的是申请不是资质
def test_cert001_submitting_does_not_grant_the_certification(client, requester):
    """**这是整批的核心。** 改造前这一步直接把资质写进用户字段。"""
    worker = make_verified(client, "13600000001")
    r = apply_cert(client, worker)
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "pending"
    assert r.json()["certifications"] == [], "提交申请就拿到资质了"

    blocked = apply_to_restricted_task(client, requester, worker)
    assert blocked.status_code == 400
    assert blocked.json()["detail"]["code"] == "certification_required"


def test_cert004_only_after_approval_can_you_take_the_job(client, requester):
    worker = make_verified(client, "13600000002")
    app_id = apply_cert(client, worker).json()["id"]
    admin = make_admin(client, "13600000003")

    r = client.post(f"/api/v1/admin/certifications/{app_id}/decide",
                    json={"approve": True, "reason": "证件清晰，姓名一致"},
                    headers=auth(admin))
    assert r.status_code == 200 and r.json()["status"] == "approved"

    ok = apply_to_restricted_task(client, requester, worker)
    assert ok.status_code == 201, ok.text


def test_cert004_rejection_must_say_why(client):
    """只说「未通过」，申请人不知道该补什么，只会一遍遍重交。"""
    worker = make_verified(client, "13600000004")
    app_id = apply_cert(client, worker).json()["id"]
    admin = make_admin(client, "13600000005")
    r = client.post(f"/api/v1/admin/certifications/{app_id}/decide",
                    json={"approve": False, "reason": "   "}, headers=auth(admin))
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "reason_required"


def test_cert004_rejected_application_grants_nothing(client, requester):
    worker = make_verified(client, "13600000006")
    app_id = apply_cert(client, worker).json()["id"]
    admin = make_admin(client, "13600000007")
    client.post(f"/api/v1/admin/certifications/{app_id}/decide",
                json={"approve": False, "reason": "证件影像模糊，无法辨认编号"},
                headers=auth(admin))
    assert apply_to_restricted_task(client, requester, worker).status_code == 400


# ----------------------------------------------------- CERT-002/003 材料与姓名
def test_cert002_application_without_images_is_rejected(client):
    """没有影像，审核员看什么。"""
    worker = make_verified(client, "13600000010")
    r = apply_cert(client, worker, images=[])
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "images_required"


def test_cert003_holder_name_must_match_the_verified_identity(client):
    """**这条最容易漏，而漏了等于前面几条白做：
    一张别人的电工证也是一张真证件。**"""
    worker = make_verified(client, "13600000011", real_name="张三")
    r = apply_cert(client, worker, holder="李四")
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "holder_mismatch"
    assert "本人持有" in r.json()["detail"]["message"]

    assert apply_cert(client, worker, holder="张三").status_code == 201


def test_cert012_no_duplicate_pending_applications(client):
    worker = make_verified(client, "13600000012")
    assert apply_cert(client, worker).status_code == 201
    r = apply_cert(client, worker)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "application_pending"


# ----------------------------------------------------------------- CERT-005 有效期
def test_cert005_expired_certification_does_not_admit(client, requester):
    """**「发了就永久有效」是错的**，而且是几年后才会伤到人的错——
    到那时平台上已经有一批实际已失效的资质在照常接单。"""
    worker = make_verified(client, "13600000020")
    app_id = apply_cert(client, worker).json()["id"]
    admin = make_admin(client, "13600000021")
    client.post(f"/api/v1/admin/certifications/{app_id}/decide",
                json={"approve": True, "reason": "通过"}, headers=auth(admin))
    assert apply_to_restricted_task(client, requester, worker).status_code == 201

    from app.modules.account.models_cert import CertificationApplication

    with SessionLocal() as db:                       # 证件过期
        row = db.get(CertificationApplication, app_id)
        row.expires_at = utcnow() - timedelta(days=1)
        db.commit()

    worker2 = make_verified(client, "13600000022")   # 换个任务再试
    blocked = apply_to_restricted_task(client, requester, worker)
    assert blocked.status_code == 400, "过期资质仍然放行了"
    with SessionLocal() as db:                       # 记录仍在，只是不再满足准入
        assert db.get(CertificationApplication, app_id) is not None
        assert cert_service.active_certifications(db, worker["id"]) == []
    assert worker2  # 保持变量被使用


def test_cert005_cannot_submit_an_already_expired_certificate(client):
    worker = make_verified(client, "13600000023")
    r = apply_cert(client, worker,
                   expires_at=(utcnow() - timedelta(days=1)).isoformat())
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "certificate_expired"


def test_revoked_certification_stops_admitting(client, requester):
    worker = make_verified(client, "13600000024")
    app_id = apply_cert(client, worker).json()["id"]
    admin = make_admin(client, "13600000025")
    client.post(f"/api/v1/admin/certifications/{app_id}/decide",
                json={"approve": True, "reason": "通过"}, headers=auth(admin))
    client.post(f"/api/v1/admin/certifications/{app_id}/revoke",
                json={"approve": False, "reason": "复核发现证件系伪造"},
                headers=auth(admin))
    assert apply_to_restricted_task(client, requester, worker).status_code == 400


# ------------------------------------------- CERT-010 证件影像不能匿名读
def test_cert010_certificate_images_are_not_anonymously_readable(client):
    """`/files/{name}` 是**匿名**能力 URL，安全性只建立在「名字不可猜」上。

    对任务配图那个权衡是对的；对身份证、电工证不是——一个匿名可读的 URL
    一旦出现在日志、浏览器历史或转发的截图里，就等于把证件交出去了。
    """
    worker = make_verified(client, "13600000030")
    img = upload_image(client, worker)
    assert client.get(f"/api/v1/files/{img}").status_code == 200, "上传后本应可读"

    apply_cert(client, worker, images=[img])
    anon = client.get(f"/api/v1/files/{img}")
    assert anon.status_code == 403, "证件影像仍然可以匿名读"
    assert anon.json()["detail"]["code"] == "sensitive_file"


def test_cert010_owner_and_admin_can_read_it_through_the_secure_endpoint(client):
    """审核员要看证件才能审，所以不能「谁也不给看」，
    而是把可见范围收到最小：本人 + 管理员。"""
    worker = make_verified(client, "13600000031")
    img = upload_image(client, worker)
    apply_cert(client, worker, images=[img])
    admin = make_admin(client, "13600000032")
    other = make_verified(client, "13600000033", real_name="路人甲", nick="路人")

    assert client.get(f"/api/v1/files/{img}/secure", headers=auth(worker)).status_code == 200
    assert client.get(f"/api/v1/files/{img}/secure", headers=auth(admin)).status_code == 200
    assert client.get(f"/api/v1/files/{img}/secure", headers=auth(other)).status_code == 403
    assert client.get(f"/api/v1/files/{img}/secure").status_code == 403   # 未登录


def test_cert010_sensitive_files_are_not_cached(client):
    """敏感材料不缓存：CDN / 浏览器留一份副本就是多一个泄露点。"""
    worker = make_verified(client, "13600000034")
    img = upload_image(client, worker)
    apply_cert(client, worker, images=[img])
    r = client.get(f"/api/v1/files/{img}/secure", headers=auth(worker))
    assert "no-store" in r.headers.get("Cache-Control", "")


# ------------------------------------------------------- CERT-011 注销删证件影像
def test_cert011_deactivation_physically_removes_certificate_images(client):
    """留着一张能被管理员看的身份证，等于注销没有完成。"""
    from app.modules.account.models_cert import CertificationApplication

    worker = make_verified(client, "13600000040")
    img = upload_image(client, worker)
    app_id = apply_cert(client, worker, images=[img]).json()["id"]

    assert client.post("/api/v1/users/me/deactivate",
                       headers=auth(worker)).status_code == 200
    with SessionLocal() as db:
        row = db.get(CertificationApplication, app_id)
        assert row is not None, "申请记录该保留（审计需要）"
        assert row.images == [], "证件影像的引用没清掉"
    # 文件本身也该没了
    assert client.get(f"/api/v1/files/{img}").status_code in (403, 404)


# ---------------------------------------------- 管理端队列：审核员要看得到关键信息
def test_admin_queue_surfaces_the_name_match(client):
    """审核员要能一眼看到「证件姓名 vs 实名」是否一致——
    让他自己去两个页面之间比对，迟早比错。"""
    worker = make_verified(client, "13600000050", real_name="张三")
    apply_cert(client, worker, holder="张三")
    admin = make_admin(client, "13600000051")
    rows = client.get("/api/v1/admin/certifications/pending", headers=auth(admin)).json()
    row = next(r for r in rows if r["user_id"] == worker["id"])
    assert row["name_matches"] is True
    assert row["real_name"] == "张三"
    # 影像链接必须指向**鉴权**端点，不是匿名能力 URL
    assert all(u.endswith("/secure") for u in row["image_urls"]), row["image_urls"]


def test_admin_queue_requires_admin(client):
    worker = make_verified(client, "13600000052")
    assert client.get("/api/v1/admin/certifications/pending",
                      headers=auth(worker)).status_code == 403


# ------------------------------------------------- CERT-006 存量数据不再生效
def test_cert006_admission_reads_the_application_table_not_the_snapshot(client, requester):
    """存量 `users.certifications` 是用户自己 POST 进去的。

    准入判断改读申请表之后，**直接往快照字段里塞名字不再有任何作用**——
    这正是迁移能安全清空它的前提。
    """
    from app.modules.account.models import User

    worker = make_verified(client, "13600000060")
    with SessionLocal() as db:                    # 模拟历史遗留的自助资质
        u = db.get(User, worker["id"])
        u.certifications = ["电工"]
        db.commit()

    blocked = apply_to_restricted_task(client, requester, worker)
    assert blocked.status_code == 400, "往快照字段塞个名字就能接电工单"
    assert blocked.json()["detail"]["code"] == "certification_required"


def test_unrestricted_categories_are_unaffected(client, requester):
    """别把门关过头：普通类目不该受影响。"""
    worker = make_verified(client, "13600000061")
    task = publish_task(client, requester, category="保洁")
    r = client.post(f"/api/v1/tasks/{task['id']}/applications",
                    json={"message": "我可以做"}, headers=auth(worker))
    assert r.status_code == 201, r.text


def test_expiring_soon_finds_certificates_about_to_lapse(client):
    """CERT-005 到期前要提醒，给人时间去复审。"""
    from app.modules.account.models_cert import CertificationApplication

    worker = make_verified(client, "13600000070")
    app_id = apply_cert(client, worker).json()["id"]
    admin = make_admin(client, "13600000071")
    client.post(f"/api/v1/admin/certifications/{app_id}/decide",
                json={"approve": True, "reason": "通过"}, headers=auth(admin))
    with SessionLocal() as db:
        db.get(CertificationApplication, app_id).expires_at = utcnow() + timedelta(days=10)
        db.commit()
        soon = cert_service.expiring_soon(db, days=30)
        assert any(r.id == app_id for r in soon)
        assert not any(r.id == app_id for r in cert_service.expiring_soon(db, days=5))
