"""CNT-003 博客编辑器与草稿箱 / CNT-014 视频（44 号 spec）。

需求回顾查出的最后两条降级实现。原 spec 写的是
「博客编辑器：Markdown/富文本，**草稿箱**，**插图**，标签」——
而 `contents` 表此前连存媒体的字段都没有，`status` 也只有 published/removed。
插图、视频、草稿箱三件事全都无从谈起。
"""
import base64
import os

from .conftest import auth, register

PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x11" * 96).decode()
WEB_SRC = os.path.join(os.path.dirname(__file__), "..", "..", "web", "src")


def strip_comments(src: str) -> str:
    """去掉 // 行注释。断言要钉的是代码，不是描述代码的散文。"""
    return "\n".join(line.split("//")[0] for line in src.splitlines())


def blog(client, u, **over):
    payload = {"kind": "blog", "title": "我的保洁心得", "body": "先除尘再湿擦。",
               "tags": ["保洁"], **over}
    return client.post("/api/v1/contents", json=payload, headers=auth(u))


# ---------- CNT-003 草稿箱 ----------
def test_cnt003_draft_is_invisible_to_everyone_else(client):
    """草稿不是「还没推荐」，是「还没公开」。"""
    a = register(client, "13988800001", "作者")
    b = register(client, "13988800002", "别人")
    r = blog(client, a, publish=False)
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    assert r.json()["status"] == "draft"

    # feed 里没有
    assert cid not in [c["id"] for c in client.get("/api/v1/feed", headers=auth(b)).json()]
    # 他人主页没有
    assert cid not in [c["id"] for c in
                       client.get(f"/api/v1/users/{a['id']}/contents", headers=auth(b)).json()]
    # 直接猜 id 也打不开
    assert client.get(f"/api/v1/contents/{cid}", headers=auth(b)).status_code == 404
    # 但作者自己打得开——否则草稿箱里点进去是 404，没法编辑
    assert client.get(f"/api/v1/contents/{cid}", headers=auth(a)).status_code == 200


def test_cnt003_draft_box_lists_only_my_drafts(client):
    a = register(client, "13988800003", "作者")
    b = register(client, "13988800004", "另一个作者")
    blog(client, a, publish=False, title="甲的草稿")
    blog(client, b, publish=False, title="乙的草稿")
    mine = client.get("/api/v1/contents/mine?status=draft", headers=auth(a)).json()
    assert [m["title"] for m in mine] == ["甲的草稿"]


def test_cnt003_edit_then_publish(client):
    a = register(client, "13988800005", "作者")
    cid = blog(client, a, publish=False).json()["id"]
    r = client.patch(f"/api/v1/contents/{cid}",
                     json={"body": "改过的正文", "tags": ["保洁", "经验"]}, headers=auth(a))
    assert r.status_code == 200 and r.json()["body"] == "改过的正文"

    r = client.post(f"/api/v1/contents/{cid}/publish", headers=auth(a))
    assert r.status_code == 200 and r.json()["status"] == "published"
    b = register(client, "13988800006", "读者")
    assert client.get(f"/api/v1/contents/{cid}", headers=auth(b)).status_code == 200


def test_cnt003_publishing_reruns_moderation(client):
    """草稿是随便改的——存草稿时审过不算数。

    「先存一段干净的，再编辑成违规的，然后发布」是条现成的绕过。
    """
    a = register(client, "13988800007", "作者")
    cid = blog(client, a, publish=False).json()["id"]
    # 直接改库绕过 patch 的机审，模拟「草稿是从别的路径变脏的」
    from app.core.db import SessionLocal
    from app.modules.content.models import Content
    from app.modules.task.service import BANNED_WORDS

    db = SessionLocal()
    row = db.get(Content, cid)
    row.body = f"正文含{list(BANNED_WORDS)[0]}"
    db.add(row)
    db.commit()
    db.close()

    r = client.post(f"/api/v1/contents/{cid}/publish", headers=auth(a))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "content_rejected"


def test_cnt003_edit_reruns_moderation_too(client):
    a = register(client, "13988800008", "作者")
    from app.modules.task.service import BANNED_WORDS

    cid = blog(client, a, publish=False).json()["id"]
    r = client.patch(f"/api/v1/contents/{cid}",
                     json={"body": f"改成{list(BANNED_WORDS)[0]}"}, headers=auth(a))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "content_rejected"


def test_cnt003_only_author_can_edit_or_publish(client):
    a = register(client, "13988800009", "作者")
    b = register(client, "13988800010", "路人")
    cid = blog(client, a, publish=False).json()["id"]
    assert client.patch(f"/api/v1/contents/{cid}", json={"body": "改"},
                        headers=auth(b)).status_code in (403, 404)
    assert client.post(f"/api/v1/contents/{cid}/publish",
                       headers=auth(b)).status_code in (403, 404)


# ---------- CNT-003 插图 ----------
def test_cnt003_content_can_carry_images(client):
    """此前 contents 表压根没有存媒体的地方。"""
    a = register(client, "13988800011", "作者")
    url = client.post("/api/v1/files",
                      json={"content_type": "image/png", "data_base64": PNG},
                      headers=auth(a)).json()["url"]
    r = blog(client, a, media_urls=[url])
    assert r.status_code == 201
    assert r.json()["media_urls"] == [url]


# ---------- CNT-014 视频 ----------
def test_cnt014_video_does_not_go_through_the_base64_path(client):
    """50MB 的视频 base64 后是 67MB 的 JSON 体——几个并发就能把进程打死。"""
    a = register(client, "13988800012", "视频作者")
    r = client.post("/api/v1/files",
                    json={"content_type": "video/mp4", "data_base64": PNG}, headers=auth(a))
    assert r.status_code == 422 or r.status_code == 400, r.text


def test_cnt014_local_storage_says_it_cannot_do_direct_upload(client):
    """本地没有 CDN 就**明确失败**，而不是给一个假 URL 让客户端传到不存在的地方。"""
    a = register(client, "13988800013", "视频作者")
    r = client.post("/api/v1/files/sign-upload",
                    json={"content_type": "video/mp4", "size_bytes": 5_000_000},
                    headers=auth(a))
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "direct_upload_unsupported"
    assert "没有 CDN" in r.json()["detail"]["message"]


def test_cnt014_oversized_and_wrong_type_refused(client):
    a = register(client, "13988800014", "视频作者")
    big = client.post("/api/v1/files/sign-upload",
                      json={"content_type": "video/mp4", "size_bytes": 999_000_000},
                      headers=auth(a))
    assert big.status_code == 400 and big.json()["detail"]["code"] == "too_large"
    bad = client.post("/api/v1/files/sign-upload",
                      json={"content_type": "application/zip", "size_bytes": 100},
                      headers=auth(a))
    assert bad.status_code == 422


# ---------- Markdown 渲染的安全性 ----------
def test_cnt003_markdown_renderer_never_uses_innerhtml():
    """博客正文是别人写的、所有人都会看——转 HTML 塞进 DOM 就是存储型 XSS。

    这条钉的是**手段**而不是结果：只要没有 `dangerouslySetInnerHTML`，
    XSS 这个类别在这条路径上就不存在，不必依赖某个 sanitizer 的黑名单。
    """
    # 只看代码，不看注释——注释里正解释着「绝不用 dangerouslySetInnerHTML」。
    # V58 踩过同一个坑：断言命中了描述旧代码的那段散文。
    code = strip_comments(open(os.path.join(WEB_SRC, "Markdown.tsx")).read())
    assert "dangerouslySetInnerHTML" not in code
    assert "innerHTML" not in code


def test_cnt003_markdown_renderer_filters_link_protocols():
    """`javascript:` 开头的 href 不需要 innerHTML 也能执行。"""
    src = open(os.path.join(WEB_SRC, "Markdown.tsx")).read()
    assert "SAFE_URL" in src and "https?" in src
    assert "safeUrl" in src


def test_cnt003_blog_editor_has_the_four_things_the_spec_asked_for():
    """Markdown 预览 / 草稿箱 / 插图 / 标签——原 spec 四件事一件不少。"""
    src = open(os.path.join(WEB_SRC, "BlogEditor.tsx")).read()
    assert "<Markdown" in src                    # Markdown 预览
    assert "myDrafts" in src and "草稿箱" in src   # 草稿箱
    assert "PhotoPicker" in src                  # 插图
    assert "标签" in src                          # 标签
    assert "publishContent" in src
