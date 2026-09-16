"""UMOD-010~042 上传图片的内容审核与处置（39 号 spec）。

平台有内容安全供应商抽象、有举报流程、有审核队列、生产启动自检把
`moderation` 列为 P0 能力——**但图片从来不过审核**。

全仓唯一一处调用是 `check("text", text)`，只有任务文本。而 `check()` 的
第三个参数就叫 `media_urls`，`LocalModerationProvider` 里甚至专门为它写了
「看不了图 → 标记人审，而不是假装通过」的分支——**那段分支从来没有被执行过**，
因为没有任何调用方传 `media_urls`。

接口预留了、桩实现写好了、生产自检拦着不让用 mock，唯独没人调用。
"""
import base64
import os

import pytest
import sqlalchemy as sa

from app.core.db import SessionLocal, engine
from app.modules.files.models import UploadedFile
from app.vendors import registry
from app.vendors.base import VendorError, VendorResult

from .conftest import auth, register

RAW = b"\x89PNG\r\n\x1a\n" + b"\x07" * 96
B64 = base64.b64encode(RAW).decode()


def upload(client, user):
    return client.post("/api/v1/files",
                       json={"content_type": "image/png", "data_base64": B64},
                       headers=auth(user))


def make_admin(client, phone="13844400099"):
    admin = register(client, phone, "审核员")
    with engine.begin() as conn:
        conn.execute(sa.text("UPDATE users SET is_admin = 1 WHERE id = :id"), {"id": admin["id"]})
    return admin


class _Moderation:
    """按需给出裁决的审核桩。"""

    name = "local"

    def __init__(self, status="pass", labels=None, raises=False):
        self.status, self.labels, self.raises = status, labels or [], raises
        self.calls = []

    def check(self, kind, text, media_urls=None):
        self.calls.append((kind, text, media_urls))
        if self.raises:
            raise VendorError("upstream_down", "内容安全服务不可用", retryable=True)
        return VendorResult(ok=True, external_ref="stub", status=self.status,
                            data={"labels": self.labels})


@pytest.fixture()
def moderation(monkeypatch):
    """把 moderation 换成可控桩；返回一个可改 status 的对象。"""
    stub = _Moderation()

    def fake(kind):
        return stub if kind == "moderation" else _real(kind)

    _real = registry.get_provider
    monkeypatch.setattr(registry, "get_provider", fake)
    import app.modules.files.router as files_router
    monkeypatch.setattr(files_router, "get_provider", fake)
    return stub


def storage_root():
    from app.vendors.registry import get_provider

    p = get_provider("storage")
    return getattr(p, "root", None) or p._local.root


# ---------- UMOD-042 media_urls 真的被传下去了 ----------
def test_umod042_moderation_actually_receives_the_image_url(client, moderation):
    """这条专门防「又一次建好了没接上」。

    本地实现里为 `media_urls` 写的那段分支，改造前一次都没跑过。
    """
    user = register(client, "13844400001", "上传者")
    assert upload(client, user).status_code == 201
    assert moderation.calls, "上传根本没有调用内容审核"
    kind, _text, media_urls = moderation.calls[-1]
    assert kind == "image"
    assert media_urls and media_urls[0].startswith("/api/v1/files/")


# ---------- UMOD-011/040 reject 不留痕迹 ----------
def test_umod011_rejected_upload_is_refused_and_leaves_nothing_behind(client, moderation):
    moderation.status, moderation.labels = "reject", ["涉政", "涉黄"]
    user = register(client, "13844400002", "违规上传")
    # 上传目录在整个测试会话里是共享的，所以比的是**这次**有没有多出文件
    before = set(os.listdir(storage_root())) if os.path.isdir(storage_root()) else set()

    r = upload(client, user)
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "moderation_rejected"
    assert "涉政" in r.json()["detail"]["message"]     # 告诉用户命中了什么

    db = SessionLocal()
    assert db.query(UploadedFile).count() == 0, "被拒的上传不该落库"
    db.close()
    added = {n for n in set(os.listdir(storage_root())) - before if n.endswith(".png")}
    assert not added, f"被拒的文件仍留在磁盘：{added}"


def test_umod041_rejecting_one_upload_does_not_break_another_users_copy(client, moderation):
    """甲的图被删，乙上传过的同一份内容仍然读得到。

    这正是 V62 改用随机名 + 硬链接的目的：删掉一个名字不影响别的名字。
    """
    good = register(client, "13844400003", "乙")
    kept = upload(client, good).json()["url"]

    moderation.status = "reject"
    bad = register(client, "13844400004", "甲")
    assert upload(client, bad).status_code == 400

    assert client.get(kept).status_code == 200, "删甲的名字把乙的内容一起删了"
    assert client.get(kept).content == RAW


# ---------- UMOD-012 review 放行进队列 ----------
def test_umod012_review_passes_through_but_lands_in_the_queue(client, moderation):
    """`review` 的语义是「机器拿不准，交给人」，不是拒绝。

    本地实现对任何图片都返回 review——把它当拒绝会让所有非生产部署
    完全传不了图，那不是安全，是瘫痪。
    """
    moderation.status, moderation.labels = "review", ["media_not_inspectable"]
    user = register(client, "13844400005", "待审")
    r = upload(client, user)
    assert r.status_code == 201
    assert client.get(r.json()["url"]).status_code == 200      # 用户侧照常可用

    admin = make_admin(client)
    pending = client.get("/api/v1/admin/uploads/pending", headers=auth(admin)).json()
    assert [p["name"] for p in pending] == [r.json()["ref"]]
    assert pending[0]["owner_id"] == user["id"]
    assert "media_not_inspectable" in pending[0]["labels"]


# ---------- UMOD-013 供应商故障 fail open ----------
def test_umod013_provider_failure_does_not_block_the_upload(client, moderation):
    """交付凭证传不上去等于没有证据——第三方抖一下的代价不该落在被侵害方身上。"""
    moderation.raises = True
    user = register(client, "13844400006", "凭证上传")
    r = upload(client, user)
    assert r.status_code == 201, r.text

    db = SessionLocal()
    row = db.get(UploadedFile, r.json()["ref"])
    db.close()
    assert row.moderation_status == "review", "故障时必须进人审队列，而不是静默放行"
    assert any("provider_error" in x for x in row.moderation_labels)


# ---------- UMOD-021/022 审核员处置 ----------
def test_umod021_admin_reject_removes_the_file_and_tells_the_uploader(client, moderation):
    moderation.status = "review"
    user = register(client, "13844400007", "被处置者")
    r = upload(client, user).json()
    admin = make_admin(client)

    done = client.post(f"/api/v1/admin/uploads/{r['ref']}/resolve",
                       json={"action": "reject", "reason": "人工复核违规"},
                       headers=auth(admin))
    assert done.status_code == 200, done.text
    assert done.json()["file_removed"] is True
    assert client.get(r["url"]).status_code == 404

    # UMOD-022 悄悄删掉、让页面变裂图，是最差的一种处理
    titles = [n["title"] for n in client.get("/api/v1/notifications", headers=auth(user)).json()]
    assert "一张图片已被移除" in titles


def test_umod021_admin_pass_clears_it_from_the_queue(client, moderation):
    moderation.status = "review"
    user = register(client, "13844400008", "误报")
    ref = upload(client, user).json()["ref"]
    admin = make_admin(client)

    client.post(f"/api/v1/admin/uploads/{ref}/resolve",
                json={"action": "pass", "reason": "误报"}, headers=auth(admin))
    assert client.get("/api/v1/admin/uploads/pending", headers=auth(admin)).json() == []


def test_upload_queue_is_admin_only(client, moderation):
    user = register(client, "13844400009", "路人")
    assert client.get("/api/v1/admin/uploads/pending", headers=auth(user)).status_code == 403


# ---------- UMOD-030/031 存储原语 ----------
def test_umod031_delete_is_idempotent_and_refuses_traversal():
    from app.vendors.storage import LocalStorageProvider

    p = LocalStorageProvider()
    assert p.delete("no-such-file.png") is False
    assert p.delete("../../etc/passwd") is False


# ---------- 非回归 ----------
def test_normal_upload_still_works_with_the_real_local_provider(client):
    """不打桩、走真实 local 实现：它对图片返回 review，所以应当放行并入队。"""
    user = register(client, "13844400010", "常规上传")
    r = upload(client, user)
    assert r.status_code == 201, r.text
    assert client.get(r.json()["url"]).status_code == 200
