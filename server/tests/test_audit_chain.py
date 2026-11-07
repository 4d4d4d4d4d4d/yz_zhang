"""ADMIN-062 审计日志防篡改：哈希链与自检（149 号 spec）。

审计日志的承诺是「不可抵赖」。在 V177 之前它只是一张普通表：有库权限的人改一条、删一条，
事后没有任何办法知道。哈希链让每一条都依赖前一条，链头单独记最新一条：
改、删中间、删末尾、绕过接口直接插，自检都要能指出在哪里。
"""
import pytest
from sqlalchemy import text

from app.core.db import SessionLocal
from app.modules.account.models import User
from app.modules.admin.audit_chain import append, digest, verify
from app.modules.admin.models import AdminAudit, AuditChainHead
from app.modules.admin.router import record_audit
from tests.conftest import auth, make_admin

API = "/api/v1"


@pytest.fixture(autouse=True)
def _fresh_db(client):
    """每条用例一张新库（client 夹具负责重建表）。"""
    yield


def _chain(n=4):
    with SessionLocal() as db:
        for i in range(n):
            record_audit(db, 1, f"act_{i}", "user", i, f"第 {i} 条")
        db.commit()
        return [r.id for r in db.query(AdminAudit).order_by(AdminAudit.id)]


def _verify():
    with SessionLocal() as db:
        return verify(db)


def test_each_row_links_to_the_previous_one():
    ids = _chain(3)
    with SessionLocal() as db:
        rows = db.query(AdminAudit).order_by(AdminAudit.id).all()
        assert rows[0].prev_hash == "" and all(len(r.hash) == 64 for r in rows)
        assert [r.prev_hash for r in rows[1:]] == [r.hash for r in rows[:-1]]
        assert all(digest(r.prev_hash, r) == r.hash for r in rows)
        head = db.get(AuditChainHead, 1)
        assert head.last_audit_id == ids[-1] and head.last_hash == rows[-1].hash and head.count == 3
    out = _verify()
    assert out["ok"] is True and out["checked"] == 3 and out["problems"] == [] and out["head_audit_id"] == ids[-1]


def test_hash_covers_every_field():
    """少算一个字段，改那个字段就发现不了。"""
    with SessionLocal() as db:
        r = append(db, AdminAudit(admin_id=1, action="a", target_type="t", target_id=1, detail="d"))
        base = r.hash
        for field, value in [("admin_id", 2), ("action", "b"), ("target_type", "u"), ("target_id", 2),
                             ("detail", "e")]:
            old = getattr(r, field)
            setattr(r, field, value)
            assert digest(r.prev_hash, r) != base, f"改 {field} 哈希不变"
            setattr(r, field, old)
        old = r.created_at
        r.created_at = old.replace(microsecond=(old.microsecond + 1) % 1_000_000)
        assert digest(r.prev_hash, r) != base, "改时间哈希不变"
        assert digest("x" * 64, AdminAudit(admin_id=1, action="a", target_type="t", target_id=1, detail="d",
                                           created_at=old)) != base, "换上一条哈希，本条哈希不变"


def test_editing_a_row_is_detected():
    ids = _chain(4)
    with SessionLocal() as db:
        db.execute(text("UPDATE admin_audits SET detail = '改过的说明' WHERE id = :i"), {"i": ids[1]})
        db.commit()
    out = _verify()
    assert out["ok"] is False
    assert out["problems"][0]["audit_id"] == ids[1] and "被改过" in out["problems"][0]["reason"]


def test_deleting_a_middle_row_is_detected():
    ids = _chain(4)
    with SessionLocal() as db:
        db.execute(text("DELETE FROM admin_audits WHERE id = :i"), {"i": ids[1]})
        db.commit()
    out = _verify()
    assert out["ok"] is False
    assert out["problems"][0]["audit_id"] == ids[2] and "被删" in out["problems"][0]["reason"]


def test_deleting_the_tail_is_detected_by_the_head():
    """删最后几条，剩下的链本身是完整的——只有链头知道少了。"""
    ids = _chain(4)
    with SessionLocal() as db:
        db.execute(text("DELETE FROM admin_audits WHERE id >= :i"), {"i": ids[2]})
        db.commit()
    out = _verify()
    assert out["ok"] is False and out["checked"] == 2
    assert out["problems"][0]["audit_id"] == ids[-1] and "最后几条被删了" in out["problems"][0]["reason"]


def test_a_row_inserted_around_the_interface_is_detected():
    ids = _chain(2)
    with SessionLocal() as db:
        db.add(AdminAudit(admin_id=1, action="sneaky", target_type="user", target_id=9, detail="直接插库"))
        db.commit()
        sneaky = db.query(AdminAudit).filter(AdminAudit.action == "sneaky").one().id
    _chain(1)   # 之后又有正常写入：插进来的那条夹在链中间
    out = _verify()
    assert out["ok"] is False and sneaky > ids[-1]
    assert any(p["audit_id"] == sneaky and "绕过" in p["reason"] for p in out["problems"])


def test_legacy_rows_before_the_chain_are_counted_not_flagged():
    """V177 之前的旧记录没有哈希：在链开始之前的不算断点，单独计数。"""
    with SessionLocal() as db:
        db.add_all([AdminAudit(admin_id=1, action="old", detail="旧"), AdminAudit(admin_id=1, action="old", detail="旧")])
        db.commit()
    _chain(2)
    out = _verify()
    assert out["ok"] is True and out["legacy_unchained"] == 2 and out["checked"] == 2


def test_verify_endpoint_is_compliance_only_and_is_itself_audited(client):
    comp = make_admin(client, "13800240001", "合规")
    fin = make_admin(client, "13800240002", "财务")
    with SessionLocal() as db:
        db.get(User, comp["id"]).admin_roles = ["compliance"]
        db.get(User, fin["id"]).admin_roles = ["finance"]
        db.commit()
    url = f"{API}/admin/audit-log/verify"
    assert client.get(url, headers=auth(fin)).status_code == 403
    r = client.get(url, headers=auth(comp))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(body, "AuditChainReport")
    with SessionLocal() as db:
        row = db.query(AdminAudit).filter(AdminAudit.action == "verify_audit_log").one()
        assert row.admin_id == comp["id"] and "完整" in row.detail and row.hash
    # 自检这一条也在链上：再查一次仍然完整，且多走了一条
    again = client.get(url, headers=auth(comp)).json()
    assert again["ok"] is True and again["checked"] == body["checked"] + 1
