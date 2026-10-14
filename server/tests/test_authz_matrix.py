"""SEC-061 授权总表与代码对得上（114 号 spec，docs/AUTHZ-MATRIX.md）。

台账原话：授权判据三种混用，**没有一份总表**；其中「管理员能不能看私聊与证件影像」必须有明文——
**沉默等于默认可以**。量过之后确实如此：任何管理员都能读任何人的私聊（连撤回的原文）、
往别人的私聊里发消息、读任何人的证件影像，而且都不留痕。

闸门：
1. 代码里每一处「管理员绕过」（`not user.is_admin` / `or user.is_admin`）都在总表第 3 节有一行，反之亦然；
2. 第 3.2 节「受限」的每一处都真的调用审计；
3. 行为：管理员不写理由读不了别人的私聊、写了理由能读且进审计、任何情况下不能往别人的私聊里发消息；
   管理员在自己的私聊里看不到对方撤回的原文；读与资质审核无关的证件影像要理由。
"""
import ast
import re
from pathlib import Path

from app.core.db import SessionLocal
from tests.conftest import auth, make_admin, register

ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT.parent / "docs" / "AUTHZ-MATRIX.md"
# 定义「管理员」这个角色本身的地方，不是绕过
ROLE_DEFINITIONS = {"app/core/deps.py::require_admin", "app/modules/admin/router.py::_job_or_admin",
                    "app/core/admin_roles.py::roles_of"}   # SEC-061b 角色定义本身（141 号 spec）


def _bypasses() -> set[str]:
    out = set()
    for path in (ROOT / "app").rglob("*.py"):
        src = path.read_text(encoding="utf-8")
        for fn in ast.walk(ast.parse(src)):
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                body = ast.get_source_segment(src, fn) or ""
                if re.search(r"not user\.is_admin|or user\.is_admin", body):
                    out.add(f"{path.relative_to(ROOT).as_posix()}::{fn.name}")
    return out - ROLE_DEFINITIONS


def _matrix_rows() -> dict[str, str]:
    text = MATRIX.read_text(encoding="utf-8")
    restricted_at = text.index("### 3.2")
    rows = {}
    for m in re.finditer(r"\| `([a-z_]+/[a-z_]+\.py::[A-Za-z_]+)` \|", text):
        rows[f"app/modules/{m.group(1)}"] = "restricted" if m.start() > restricted_at else "oversight"
    return rows


def test_the_scanner_sees_the_bypasses():
    assert "app/modules/im/router.py::_get_conv" in _bypasses()


def test_every_admin_bypass_is_written_down_and_vice_versa():
    code, doc = _bypasses(), set(_matrix_rows())
    missing = sorted(code - doc)
    assert not missing, ("这些地方让管理员绕过了归属检查，却没写进 docs/AUTHZ-MATRIX.md 第 3 节：\n  "
                         + "\n  ".join(missing) + "\n写明它属于「职责内」还是「受限（写理由 + 审计）」。")
    stale = sorted(doc - code)
    assert not stale, f"总表里写着、代码里已经没有的：{stale}"


def test_restricted_admin_access_is_audited_in_code():
    for where, kind in _matrix_rows().items():
        if kind != "restricted":
            continue
        path, fn = where.split("::")
        src = (ROOT / path).read_text(encoding="utf-8")
        node = next(n for n in ast.walk(ast.parse(src))
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == fn)
        body = ast.get_source_segment(src, node) or ""
        assert "record_audit(" in body, f"{where} 是受限访问，却没有调用审计"
        assert "admin_access_reason_required" in body, f"{where} 没有「必须写理由」的拒绝分支"


# ------------------------------------------------------------------ 行为
def _audits(action: str) -> list[str]:
    from app.modules.admin.models import AdminAudit

    with SessionLocal() as db:
        return [a.detail for a in db.query(AdminAudit).filter(AdminAudit.action == action)]


def _chat(client):
    a = register(client, "13800190001", "甲")
    b = register(client, "13800190002", "乙")
    conv = client.post("/api/v1/conversations/direct", json={"user_id": b["id"]}, headers=auth(a)).json()
    m = client.post(f"/api/v1/conversations/{conv['id']}/messages", json={"content": "我的地址是某某路 1 号"},
                    headers=auth(a)).json()
    client.post(f"/api/v1/messages/{m['id']}/recall", headers=auth(a))
    client.post(f"/api/v1/conversations/{conv['id']}/messages", json={"content": "好的"}, headers=auth(b))
    return a, b, conv["id"]


def test_an_admin_needs_a_written_reason_to_read_someone_elses_chat(client):
    a, b, cid = _chat(client)
    admin = make_admin(client, "13800190009")
    url = f"/api/v1/conversations/{cid}/messages"
    r = client.get(url, headers=auth(admin))
    assert r.status_code == 403 and r.json()["detail"]["code"] == "admin_access_reason_required"
    r = client.get(url, params={"reason": "举报核查 #12：对方称被引导站外交易"}, headers=auth(admin))
    assert r.status_code == 200
    assert any(m["content"] == "我的地址是某某路 1 号" for m in r.json()), "走审计的读取能看到撤回的原文（举证用）"
    assert any("举报核查 #12" in d for d in _audits("read_private_conversation"))


def test_no_admin_can_write_into_someone_elses_chat(client):
    _a, _b, cid = _chat(client)
    admin = make_admin(client, "13800190009")
    r = client.post(f"/api/v1/conversations/{cid}/messages", json={"content": "我是管理员"}, headers=auth(admin))
    assert r.status_code == 403
    r = client.post(f"/api/v1/conversations/{cid}/read", headers=auth(admin))
    assert r.status_code == 403


def test_an_admin_does_not_see_recalled_text_in_their_own_chat(client):
    admin = make_admin(client, "13800190009")
    friend = register(client, "13800190003", "朋友")
    conv = client.post("/api/v1/conversations/direct", json={"user_id": admin["id"]}, headers=auth(friend)).json()
    m = client.post(f"/api/v1/conversations/{conv['id']}/messages", json={"content": "发错了"},
                    headers=auth(friend)).json()
    client.post(f"/api/v1/messages/{m['id']}/recall", headers=auth(friend))
    rows = client.get(f"/api/v1/conversations/{conv['id']}/messages", headers=auth(admin)).json()
    assert [r["content"] for r in rows] == ["[消息已撤回]"], "管理员身份不是在自己的私聊里看撤回原文的理由"
    assert _audits("read_private_conversation") == [], "自己的私聊不是受限访问，不进审计"


def test_reading_an_identity_image_outside_a_review_needs_a_reason(client):
    from app.modules.files.models import UploadedFile

    owner = register(client, "13800190004", "持证人")
    with SessionLocal() as db:
        db.add(UploadedFile(name="secret-id-1", owner_id=owner["id"], sha256="x", content_type="image/png",
                            size_bytes=1, moderation_status="pass", moderation_labels=[], sensitive=True))
        db.commit()
    admin = make_admin(client, "13800190009")
    r = client.get("/api/v1/files/secret-id-1/secure", headers=auth(admin))
    assert r.status_code == 403 and r.json()["detail"]["code"] == "admin_access_reason_required"
    r = client.get("/api/v1/files/secret-id-1/secure", params={"reason": "法定调取 2026-001"}, headers=auth(admin))
    assert r.status_code in (200, 404), r.text  # 本地存储里没有这个文件也无妨：鉴权已过
    assert any("法定调取" in d for d in _audits("read_sensitive_file"))
    other = register(client, "13800190005", "路人")
    assert client.get("/api/v1/files/secret-id-1/secure", headers=auth(other)).status_code == 403
