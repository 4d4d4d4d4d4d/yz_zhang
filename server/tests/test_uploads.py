"""MOB-021 / VND-031 图片上传与进度凭证。

上传端点是最容易被当成免费图床、也是最容易被塞进恶意文件的地方，
所以这里重点验的是**拒绝**：匿名拒、超限拒、类型不符拒、外链地址拒、路径穿越拒。
"""
import base64

from .conftest import auth, register, verify_user
from .test_task_flow import match_and_fund, publish_task

PNG = base64.b64encode(
    b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
).decode()
JPEG = base64.b64encode(b"\xff\xd8\xff" + b"\x00" * 64).decode()


def upload(client, user, content_type="image/png", data=PNG):
    return client.post("/api/v1/files",
                       json={"content_type": content_type, "data_base64": data},
                       headers=auth(user))


def test_upload_and_read_roundtrip(client):
    user = register(client, "13800008001", "上传者")
    r = upload(client, user)
    assert r.status_code == 201, r.text
    url = r.json()["url"]
    assert url.startswith("/api/v1/files/")

    got = client.get(url)
    assert got.status_code == 200
    assert got.headers["content-type"].startswith("image/png")
    assert "immutable" in got.headers.get("cache-control", "")


def test_upload_is_content_addressed(client):
    """同一张图重复上传只占一份空间（内容寻址）。"""
    user = register(client, "13800008002", "重复上传")
    a = upload(client, user).json()["url"]
    b = upload(client, user).json()["url"]
    assert a == b


def test_upload_requires_login(client):
    r = client.post("/api/v1/files", json={"content_type": "image/png", "data_base64": PNG})
    assert r.status_code in (401, 403)


def test_upload_rejects_type_mismatch(client):
    """声明 PNG 却塞 JPEG 字节：只信 Content-Type 等于让上传方自证清白。"""
    user = register(client, "13800008003", "类型不符")
    r = upload(client, user, content_type="image/png", data=JPEG)
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "vendor_type_mismatch"


def test_upload_rejects_non_image_type(client):
    user = register(client, "13800008004", "非图片")
    r = client.post("/api/v1/files",
                    json={"content_type": "application/pdf", "data_base64": PNG},
                    headers=auth(user))
    assert r.status_code == 422  # pydantic 模式即拦下，不进业务逻辑


def test_upload_rejects_oversize(client):
    user = register(client, "13800008005", "超大图")
    huge = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * (3 * 1024 * 1024)).decode()
    r = upload(client, user, data=huge)
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "vendor_too_large"


def test_read_rejects_path_traversal(client):
    for name in ("..%2F..%2Fetc%2Fpasswd", "....//secrets.png"):
        assert client.get(f"/api/v1/files/{name}").status_code in (400, 404)


def test_read_missing_file_404(client):
    assert client.get("/api/v1/files/deadbeef.png").status_code == 404


# ---------- 进度凭证 ----------
def test_progress_accepts_uploaded_images(client, requester, worker):
    from .conftest import topup

    topup(client, requester, 100000)
    task = publish_task(client, requester, budget_cents=30000)
    match_and_fund(client, requester, worker, task)

    url = upload(client, worker).json()["url"]
    r = client.post(f"/api/v1/tasks/{task['id']}/progress",
                    json={"content": "已到现场，附现场照", "images": [url]},
                    headers=auth(worker))
    assert r.status_code == 201, r.text

    rows = client.get(f"/api/v1/tasks/{task['id']}/progress", headers=auth(requester)).json()
    assert rows[-1]["images"] == [url]


def test_progress_rejects_external_image_url(client, requester, worker):
    """只接受本平台上传返回的相对路径：外链既不可信，也会把用户 IP 泄给第三方。"""
    from .conftest import topup

    topup(client, requester, 100000)
    task = publish_task(client, requester, budget_cents=30000)
    match_and_fund(client, requester, worker, task)

    r = client.post(f"/api/v1/tasks/{task['id']}/progress",
                    json={"content": "外链图", "images": ["https://evil.example/x.png"]},
                    headers=auth(worker))
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "invalid_image_url"


def test_progress_without_images_still_works(client, requester, worker):
    """老客户端不传 images 字段也必须正常——字段是增量，不是破坏性变更。"""
    from .conftest import topup

    topup(client, requester, 100000)
    task = publish_task(client, requester, budget_cents=30000)
    match_and_fund(client, requester, worker, task)
    r = client.post(f"/api/v1/tasks/{task['id']}/progress",
                    json={"content": "纯文字进度"}, headers=auth(worker))
    assert r.status_code == 201
    rows = client.get(f"/api/v1/tasks/{task['id']}/progress", headers=auth(worker)).json()
    assert rows[-1]["images"] == []


def test_upload_rate_limited(client):
    user = register(client, "13800008010", "刷图床")
    verify_user(client, user)
    codes = []
    for i in range(25):
        payload = base64.b64encode(b"\x89PNG\r\n\x1a\n" + bytes([i % 256]) * 64).decode()
        codes.append(upload(client, user, data=payload).status_code)
    assert 400 in codes, "上传必须限流，否则等于开了个免费图床"
