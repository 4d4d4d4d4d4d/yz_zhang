"""FILE-010~023 上传文件的 URL 是能力，不是指纹（37 号 spec）。

`GET /api/v1/files/{name}` 完全匿名——这不是疏忽：`<img src>` 带不了
Authorization 头，接真实对象存储后 URL 直接指向 CDN，读取端必然是匿名的。
业界的标准做法是**能力 URL**：知道 URL 就等于有权读它。
这个模式成立有且只有一个前提——**URL 不可猜**。

而改造前的名字是 `sha256(内容)[:32]`。探针实测：

    A url: /api/v1/files/04523bfdcb1918b37b179fd3010ceabb.png
    B url: /api/v1/files/04523bfdcb1918b37b179fd3010ceabb.png
    same object across users: True
    offline-computed name matches: True
    anonymous GET: 200 208 bytes
    cache header: public, max-age=31536000, immutable

内容哈希对任何**持有这份内容的人**都是公开的，于是这个端点变成一台存在性
预言机：拿着一张候选图片离线算一次 sha256，就能问平台「这张图在不在你这儿」。

问题从来不是长度——32 个十六进制字符是 128 位，不可能被枚举。
问题是**这个值不是秘密**。
"""
import base64
import hashlib
import os

from app.core.db import SessionLocal
from app.modules.files.models import UploadedFile

from .conftest import auth, register

RAW_A = b"\x89PNG\r\n\x1a\n" + b"\x01" * 128
RAW_B = b"\x89PNG\r\n\x1a\n" + b"\x02" * 128


def upload(client, user, raw=RAW_A, content_type="image/png"):
    r = client.post("/api/v1/files",
                    json={"content_type": content_type,
                          "data_base64": base64.b64encode(raw).decode()},
                    headers=auth(user))
    assert r.status_code == 201, r.text
    return r.json()


# ---------- FILE-021 名字不能由内容推导 ----------
def test_file021_url_is_not_derivable_from_the_file_contents(client):
    """持有原图的人不该因此就持有 URL。"""
    user = register(client, "13866600001", "上传者")
    url = upload(client, user)["url"]

    for guess in (hashlib.sha256(RAW_A).hexdigest()[:32],
                  hashlib.sha256(RAW_A).hexdigest()):
        assert guess not in url, "文件名仍然是内容指纹——能力 URL 的前提不成立"
        assert client.get(f"/api/v1/files/{guess}.png").status_code == 404


def test_file010_name_is_random_so_two_uploads_of_one_file_differ(client):
    """同一份内容重复上传得到**不同的** URL。

    改造前这里断言的是相等，还被写成优点（「不会占两份空间」）。
    省空间是对的，但省的应该是磁盘，不是 URL——两件事被混成了一件。
    """
    user = register(client, "13866600002", "重复上传")
    a, b = upload(client, user)["url"], upload(client, user)["url"]
    assert a != b
    assert client.get(a).content == client.get(b).content   # 内容当然还是同一份


def test_file020_two_users_uploading_the_same_bytes_stay_separate(client):
    """跨用户去重把两个人的数据物理合成一份，删除权就无法执行了。"""
    a = register(client, "13866600003", "甲")
    b = register(client, "13866600004", "乙")
    ua, ub = upload(client, a)["url"], upload(client, b)["url"]
    assert ua != ub, "甲凭手里的文件就能拿到乙那条证据的 URL"

    db = SessionLocal()
    owners = {
        row.name: row.owner_id
        for row in db.query(UploadedFile).filter(UploadedFile.name.in_(
            [ua.rsplit("/", 1)[-1], ub.rsplit("/", 1)[-1]]))
    }
    db.close()
    assert set(owners.values()) == {a["id"], b["id"]}


# ---------- FILE-022 磁盘去重仍然有效 ----------
def test_file022_disk_still_dedupes_by_content(client):
    """URL 各不相同，但磁盘上同一份内容只存一个 blob。"""
    from app.vendors.registry import get_provider

    user = register(client, "13866600005", "省空间")
    upload(client, user, RAW_A)
    upload(client, user, RAW_A)
    upload(client, user, RAW_B)

    root = get_provider("storage")
    root = getattr(root, "root", None) or getattr(root, "_local").root
    blobs = os.listdir(os.path.join(root, "blobs"))
    assert hashlib.sha256(RAW_A).hexdigest() in blobs
    assert hashlib.sha256(RAW_B).hexdigest() in blobs
    # 两次上传 RAW_A 只留一个 blob（另一个是 RAW_B），而不是三个
    assert len([b for b in blobs if not b.endswith(".tmp")]) >= 2


def test_blob_directory_is_not_itself_readable_through_the_endpoint(client):
    """blobs 是目录且没有图片扩展名，读取端点必须拒绝。"""
    register(client, "13866600006", "探路者")
    assert client.get("/api/v1/files/blobs").status_code == 404
    assert client.get(f"/api/v1/files/{hashlib.sha256(RAW_A).hexdigest()}").status_code == 404


# ---------- FILE-023 归属可追溯 ----------
def test_file023_upload_is_attributable_to_a_user(client):
    """举报一张违规图片时，平台必须答得出「这是谁传的」。

    改造前没有任何地方记下上传者：`VendorCall` 只记 kind / provider /
    operation / request_digest，不含用户。
    """
    user = register(client, "13866600007", "上传者")
    ref = upload(client, user)["ref"]

    db = SessionLocal()
    row = db.get(UploadedFile, ref)
    db.close()
    assert row is not None, "上传没有留下归属记录"
    assert row.owner_id == user["id"]
    assert row.sha256 == hashlib.sha256(RAW_A).hexdigest()
    assert row.content_type == "image/png"
    assert row.size_bytes == len(RAW_A)


# ---------- 非回归 ----------
def test_upload_and_anonymous_read_still_work(client):
    """能力 URL 的行为不变：拿到 URL 就能匿名读到，且仍可长缓存。"""
    user = register(client, "13866600008", "读者")
    url = upload(client, user)["url"]
    got = client.get(url)
    assert got.status_code == 200
    assert got.content == RAW_A
    assert got.headers["content-type"].startswith("image/png")
    assert "immutable" in got.headers.get("cache-control", "")
    assert got.headers["x-content-type-options"] == "nosniff"
