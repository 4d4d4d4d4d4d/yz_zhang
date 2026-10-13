"""KB-100~110 个人知识库（122 号 spec）：收件箱、检索、助手引用、纪要抽待办、方法蒸馏、导出与注销。

用户原话：「本身自己的门户就是通过助手管理和知识库的构建，这样也方便对外的合作。」
"""
from datetime import datetime

from app.core.db import SessionLocal
from app.modules.account.models import User
from app.modules.notebook import service as svc
from app.modules.notebook.models import NbMethod, NbNote
from app.modules.workbench.models import WbItem, WbLog
from tests.conftest import auth

API = "/api/v1/notebook"
WB = "/api/v1/workbench"

MINUTES = """周会纪要 10-13
- [ ] 小王 周五前 提交报价单
- [x] 已确认场地
TODO：联系财务开发票
1. 张三负责整理合同模板，10月20日前完成
2. 讨论了新品牌方向
行动项：明天发会议纪要给客户
- [ ] 小王 周五前 提交报价单
"""

SOP = """报税流程
1. 核对本月收入：银行流水与开票对一遍
2. 整理进项发票
3. 登录电子税务局申报
- 这一行是圆点，有编号时不该进方法
"""


def _note(client, user, **kw):
    r = client.post(f"{API}/notes", json=kw, headers=auth(user))
    assert r.status_code == 201, r.text
    return r.json()


# ------------------------------------------------------------------ 随手记（KB-101）
def test_capture_guesses_kind_and_title_and_never_fetches(client, requester):
    link = _note(client, requester, body="https://example.com/a/b?x=1")
    assert link["kind"] == "link" and link["url"] == "https://example.com/a/b?x=1"
    assert link["title"] == "example.com/a/b" and link["body"] == "" and link["status"] == "inbox"
    minutes = _note(client, requester, body=MINUTES)
    assert minutes["kind"] == "minutes" and minutes["title"] == "周会纪要 10-13"
    plain = _note(client, requester, body="# 想法\n客户更在意交付时间")
    assert plain["kind"] == "note" and plain["title"] == "想法"
    r = client.post(f"{API}/notes", json={"body": "  "}, headers=auth(requester))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "note_empty"
    for bad in ("javascript:alert(1)", "file:///etc/passwd", "ftp://x.y"):
        assert client.post(f"{API}/notes", json={"url": bad}, headers=auth(requester)).status_code == 422
    # 不让客户端写不该写的字段
    assert client.post(f"{API}/notes", json={"body": "x", "owner_id": 1}, headers=auth(requester)).status_code == 422


def test_editing_files_out_of_inbox_and_stale_revision_is_refused(client, requester):
    h = auth(requester)
    n = _note(client, requester, body="随手一记")
    r = client.patch(f"{API}/notes/{n['id']}", json={"tags": ["#客户", "客户", " 报价 "], "revision": 0}, headers=h)
    assert r.status_code == 200 and r.json()["status"] == "filed" and r.json()["tags"] == ["客户", "报价"]
    r = client.patch(f"{API}/notes/{n['id']}", json={"title": "B", "revision": 0}, headers=h)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "nb_revision_conflict"
    # 只改置顶不算「整理」：仍在收件箱的那条不被挪走
    m = _note(client, requester, body="另一条")
    assert client.patch(f"{API}/notes/{m['id']}", json={"pinned": True}, headers=h).json()["status"] == "inbox"
    s = client.get(f"{API}/summary", headers=h).json()
    assert s["total"] == 2 and s["inbox"] == 1 and s["tags"] == [{"tag": "客户", "count": 1}, {"tag": "报价", "count": 1}]


def test_note_limit(client, requester, monkeypatch):
    monkeypatch.setitem(svc.LIMITS, "notes", 1)
    _note(client, requester, body="一")
    r = client.post(f"{API}/notes", json={"body": "二"}, headers=auth(requester))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "nb_limit_reached"


# ------------------------------------------------------------------ 检索（KB-102）
def test_search_chinese_substrings_ranks_title_first_and_hides_archived(client, requester):
    h = auth(requester)
    in_body = _note(client, requester, title="本月待办", body="这个月要做增值税申报，记得带上进项发票")
    in_title = _note(client, requester, title="增值税小规模纳税人减免", body="季度销售额不超过一定额度免征")
    old = _note(client, requester, body="去年的增值税资料")
    client.patch(f"{API}/notes/{old['id']}", json={"status": "archived"}, headers=h)
    _note(client, requester, body="和增值无关的东西")
    hits = client.get(f"{API}/notes", params={"q": "增值税"}, headers=h).json()
    assert [x["id"] for x in hits] == [in_title["id"], in_body["id"]]
    assert "增值税申报" in hits[1]["excerpt"]
    # 长查询也能命中：切成二字后仍然认得「申报」
    assert in_body["id"] in [x["id"] for x in client.get(f"{API}/notes", params={"q": "个税申报"}, headers=h).json()]
    archived = client.get(f"{API}/notes", params={"status": "archived"}, headers=h).json()
    assert [x["id"] for x in archived] == [old["id"]]


def test_tag_and_kind_filters(client, requester):
    h = auth(requester)
    a = _note(client, requester, body="甲", tags=["客户"])
    _note(client, requester, body="乙", tags=["自己"])
    link = _note(client, requester, body="https://example.org/x", tags=["客户"])
    assert {x["id"] for x in client.get(f"{API}/notes", params={"tag": "客户"}, headers=h).json()} == {a["id"], link["id"]}
    assert [x["id"] for x in client.get(f"{API}/notes", params={"kind": "link"}, headers=h).json()] == [link["id"]]


def test_terms_and_score_units():
    ts = svc.terms("增值税申报 VAT")
    assert ("增值税申报", 3, 0) in ts and ("增值", 1, 0) in ts and ("税申", 1, 0) in ts and ("vat", 3, 1) in ts
    n = NbNote(title="增值税", body="", url="", tags=[])
    m = NbNote(title="", body="增值税", url="", tags=[])
    assert svc.score(n, svc.terms("增值税")) > svc.score(m, svc.terms("增值税")) > 0
    assert svc.terms("专票要什么")[0][0] == "专票"      # 提问里的虚词去掉
    assert svc.terms("十月报税")[0][0] == "报税" and svc.terms("本周周报")[0][0] == "周报"   # 时间词去掉，主题留下
    # 只沾一个二字边（1/2 < 60%）不算相关；三个切片中两个（≥60%）算
    assert svc.score(NbNote(title="", body="增值无关", url="", tags=[]), svc.terms("增值税")) == 0
    assert svc.score(NbNote(title="", body="增值税申报", url="", tags=[]), svc.terms("个税申报")) > 0


# ------------------------------------------------------------------ 只属于本人（KB-109）
def test_other_people_get_404_and_global_search_never_sees_notes(client, requester, worker):
    n = _note(client, requester, title="罕见的私人笔记词", body="银行卡密码提示")
    hw = auth(worker)
    for method, url, body in (("get", f"{API}/notes/{n['id']}", None),
                              ("patch", f"{API}/notes/{n['id']}", {"title": "x"}),
                              ("delete", f"{API}/notes/{n['id']}", None),
                              ("post", f"{API}/notes/{n['id']}/extract-todos", None),
                              ("post", f"{API}/notes/{n['id']}/todos", {"items": [{"title": "x"}]}),
                              ("post", f"{API}/methods/distill", {"note_ids": [n["id"]]})):
        r = getattr(client, method)(url, headers=hw, **({"json": body} if body is not None else {}))
        assert r.status_code == 404, (method, url, r.status_code)
    assert client.get(f"{API}/notes", params={"q": "罕见的私人笔记词"}, headers=hw).json() == []
    assert client.post(f"{API}/ask", json={"q": "罕见的私人笔记词"}, headers=hw).json()["citations"] == []
    # 全站搜索不收个人笔记
    r = client.get("/api/v1/search", params={"q": "罕见的私人笔记词"}, headers=auth(requester))
    assert "罕见的私人笔记词" not in r.text
    # 蒸馏时混进别人的笔记：整批 404，而不是悄悄丢掉
    mine = _note(client, worker, body="1. 步骤")
    r = client.post(f"{API}/methods/distill", json={"note_ids": [mine["id"], n["id"]]}, headers=hw)
    assert r.status_code == 404


# ------------------------------------------------------------------ 助手引用（KB-104）
def test_ask_cites_sources_and_refuses_to_make_things_up(client, requester):
    h = auth(requester)
    a = _note(client, requester, title="开票规则", body="给企业客户开专票，要税号和开户行")
    _note(client, requester, body="周末去爬山")
    r = client.post(f"{API}/ask", json={"q": "专票要什么"}, headers=h).json()
    assert r["mode"] == "extractive" and [c["note_id"] for c in r["citations"]] == [a["id"]]
    assert "[1] 开票规则" in r["answer"] and "税号" in r["citations"][0]["snippet"]
    none = client.post(f"{API}/ask", json={"q": "量子计算"}, headers=h).json()
    assert none["citations"] == [] and "还没有" in none["answer"]


def test_workbench_breakdown_and_related_cite_my_notes(client, requester, worker):
    h = auth(requester)
    note = _note(client, requester, title="报税材料清单", body="报税要准备：银行流水、发票、上季度申报表")
    _note(client, requester, body="周末去爬山")
    item = client.post(f"{WB}/items", json={"title": "整理报税材料"}, headers=h).json()
    rel = client.get(f"{API}/related", params={"item_id": item["id"]}, headers=h).json()
    assert [x["note_id"] for x in rel] == [note["id"]]
    draft = client.post(f"{WB}/items/{item['id']}/breakdown", headers=h).json()
    assert draft["steps"] and [x["note_id"] for x in draft["references"]] == [note["id"]]
    # 别人的任务：404
    assert client.get(f"{API}/related", params={"item_id": item["id"]}, headers=auth(worker)).status_code == 404


# ------------------------------------------------------------------ 纪要抽待办（KB-105）
def test_due_hint_units():
    # 2026-10-13 是周二；UTC 02:00 = 北京 10:00
    now = datetime(2026, 10, 13, 2, 0)
    assert svc.due_hint("周五前提交", now) == datetime(2026, 10, 16, 10, 0)     # 北京 18:00
    assert svc.due_hint("下周三", now) == datetime(2026, 10, 21, 10, 0)
    assert svc.due_hint("明天发", now) == datetime(2026, 10, 14, 10, 0)
    assert svc.due_hint("10月20日前", now) == datetime(2026, 10, 20, 10, 0)
    assert svc.due_hint("1/5 之前", now) == datetime(2027, 1, 5, 10, 0)        # 已过去很久 → 明年
    assert svc.due_hint("2月30日", now) is None and svc.due_hint("尽快", now) is None
    assert svc.due_hint("版本 1/2/3", now) is None


def test_extract_todos_is_a_draft_then_confirmed_into_workbench(client, requester):
    h = auth(requester)
    n = _note(client, requester, body=MINUTES)
    draft = client.post(f"{API}/notes/{n['id']}/extract-todos", headers=h).json()["items"]
    titles = [x["title"] for x in draft]
    assert titles == ["小王 周五前 提交报价单", "联系财务开发票", "张三负责整理合同模板，10月20日前完成",
                      "明天发会议纪要给客户"]
    assert draft[0]["due_at"] and draft[1]["due_at"] is None and draft[2]["due_at"].startswith("2026-10-20")
    with SessionLocal() as db:
        assert db.query(WbItem).count() == 0       # 草稿不写库
    r = client.post(f"{API}/notes/{n['id']}/todos",
                    json={"items": [{"title": draft[0]["title"], "due_at": draft[0]["due_at"]},
                                    {"title": "联系财务开发票（改过）"}]}, headers=h)
    assert r.status_code == 201 and [x["title"] for x in r.json()] == ["小王 周五前 提交报价单", "联系财务开发票（改过）"]
    assert r.json()[0]["due_at"] == draft[0]["due_at"] and "周会纪要" in r.json()[0]["notes"]
    with SessionLocal() as db:
        assert db.query(WbLog).filter(WbLog.kind == "assistant").count() == 2


# ------------------------------------------------------------------ 方法蒸馏与套用（KB-106 / KB-107）
def test_distill_prefers_numbered_steps_and_splits_notes(client, requester):
    h = auth(requester)
    a = _note(client, requester, body=SOP)
    b = _note(client, requester, body="1. 整理进项发票\n2. 留存申报回执")
    d = client.post(f"{API}/methods/distill", json={"note_ids": [a["id"], b["id"]]}, headers=h).json()
    assert d["found"] == "numbered" and d["name"] == "报税流程" and d["source_note_ids"] == [a["id"], b["id"]]
    assert [s["title"] for s in d["steps"]] == ["核对本月收入", "整理进项发票", "登录电子税务局申报", "留存申报回执"]
    assert d["steps"][0]["note"] == "银行流水与开票对一遍"
    bullets = _note(client, requester, title="出差", body="- 身份证\n- 充电器\n- [x] 已订酒店")
    d2 = client.post(f"{API}/methods/distill", json={"note_ids": [bullets["id"]]}, headers=h).json()
    assert d2["found"] == "bullets" and d2["name"] == "出差的做法" and [s["title"] for s in d2["steps"]] == ["身份证", "充电器"]
    empty = _note(client, requester, body="没有任何列表的一段话")
    d3 = client.post(f"{API}/methods/distill", json={"note_ids": [empty["id"]]}, headers=h).json()
    assert d3["found"] == "none" and d3["steps"] == []
    with SessionLocal() as db:
        assert db.query(NbMethod).count() == 0     # 草稿不写库


def test_method_applies_to_workbench_item_as_checklist(client, requester, worker):
    h = auth(requester)
    m = client.post(f"{API}/methods", json={"name": "报税流程", "steps": [{"title": "核对收入"}, {"title": "申报"}]},
                    headers=h)
    assert m.status_code == 201
    mid = m.json()["id"]
    item = client.post(f"{WB}/items", json={"title": "十月报税"}, headers=h).json()
    r = client.post(f"{API}/methods/{mid}/apply", json={"item_id": item["id"]}, headers=h)
    assert r.status_code == 201 and [c["title"] for c in r.json()["children"]] == ["核对收入", "申报"]
    assert client.get(f"{API}/methods", headers=h).json()[0]["uses"] == 1
    # 子项上不能再套（清单只有一层），别人的任务与别人的方法都是 404
    child = r.json()["children"][0]["id"]
    assert client.post(f"{API}/methods/{mid}/apply", json={"item_id": child}, headers=h).json()["detail"]["code"] == "only_one_level"
    other = client.post(f"{WB}/items", json={"title": "别人的"}, headers=auth(worker)).json()
    assert client.post(f"{API}/methods/{mid}/apply", json={"item_id": other["id"]}, headers=h).status_code == 404
    assert client.post(f"{API}/methods/{mid}/apply", json={"item_id": other["id"]}, headers=auth(worker)).status_code == 404
    p = client.patch(f"{API}/methods/{mid}", json={"steps": [{"title": "只剩一步"}]}, headers=h).json()
    assert [s["title"] for s in p["steps"]] == ["只剩一步"]
    assert client.delete(f"{API}/methods/{mid}", headers=auth(worker)).status_code == 404
    assert client.delete(f"{API}/methods/{mid}", headers=h).json() == {"deleted": True}


# ------------------------------------------------------------------ 导出与注销（KB-108 / KB-109）
def test_export_markdown_and_personal_data_export(client, requester):
    h = auth(requester)
    _note(client, requester, title="开票规则", body="专票要税号", tags=["财税"])
    client.post(f"{API}/methods", json={"name": "报税流程", "steps": [{"title": "申报", "note": "月初"}]}, headers=h)
    md = client.get(f"{API}/export", headers=h).json()
    assert md["notes"] == 1 and md["methods"] == 1 and md["filename"].endswith(".md")
    assert "## 开票规则" in md["markdown"] and "标签：财税" in md["markdown"] and "1. 申报：月初" in md["markdown"]
    full = client.get("/api/v1/users/me/export", headers=h).json()
    assert full["notebook"]["notes"][0]["body"] == "专票要税号" and full["notebook"]["methods"][0]["name"] == "报税流程"


def test_account_erase_deletes_notes_and_methods(client, requester, worker):
    from app.modules.account.deletion import erase_personal_data

    _note(client, requester, body="要被删掉的")
    _note(client, worker, body="别人的留着")
    client.post(f"{API}/methods", json={"name": "m", "steps": [{"title": "s"}]}, headers=auth(requester))
    with SessionLocal() as db:
        erase_personal_data(db, db.get(User, requester["id"]))
        db.commit()
        assert db.query(NbNote).filter(NbNote.owner_id == requester["id"]).count() == 0
        assert db.query(NbMethod).count() == 0 and db.query(NbNote).count() == 1


# ------------------------------------------------------------------ 响应形状（CLI-083：SDK 声明 vs 真实响应）
def test_responses_match_sdk_types(client, requester):
    from tests.test_client_shape_alignment import _assert_inline_shape, _assert_shape

    h = auth(requester)
    note = _note(client, requester, title="报税流程", body="1. 核对收入\n- [ ] 周五前申报", tags=["财税"])
    got = client.get(f"{API}/notes/{note['id']}", headers=h).json()
    patched = client.patch(f"{API}/notes/{note['id']}", json={"pinned": True}, headers=h).json()
    listed = client.get(f"{API}/notes", params={"q": "报税"}, headers=h).json()
    summary = client.get(f"{API}/summary", headers=h).json()
    ans = client.post(f"{API}/ask", json={"q": "报税"}, headers=h).json()
    item = client.post(f"{WB}/items", json={"title": "十月报税"}, headers=h).json()
    rel = client.get(f"{API}/related", params={"item_id": item["id"]}, headers=h).json()
    todos = client.post(f"{API}/notes/{note['id']}/extract-todos", headers=h).json()
    made = client.post(f"{API}/notes/{note['id']}/todos", json={"items": [{"title": "申报"}]}, headers=h).json()
    draft = client.post(f"{API}/methods/distill", json={"note_ids": [note["id"]]}, headers=h).json()
    method = client.post(f"{API}/methods", json={"name": "m", "steps": [{"title": "s"}]}, headers=h).json()
    methods = client.get(f"{API}/methods", headers=h).json()
    renamed = client.patch(f"{API}/methods/{method['id']}", json={"name": "n"}, headers=h).json()
    applied = client.post(f"{API}/methods/{method['id']}/apply", json={"item_id": item["id"]}, headers=h).json()
    breakdown = client.post(f"{WB}/items/{item['id']}/breakdown", headers=h).json()
    exported = client.get(f"{API}/export", headers=h).json()
    assert listed and rel and ans["citations"] and todos["items"] and made and methods

    # 第一个参数里不能有逗号：形状扫除（test_response_shape_sweep）按这一行认「已有真实响应断言」
    for payload in (note, got, patched):
        _assert_shape(payload, "NbNote")
    first_listed, first_tag, first_cite, first_rel = listed[0], summary["tags"][0], ans["citations"][0], rel[0]
    _assert_shape(first_listed, "NbNoteBrief")
    _assert_shape(summary, "NbSummary")
    _assert_shape(first_tag, "NbTagCount")
    _assert_shape(ans, "NbAnswer")
    _assert_shape(first_cite, "NbCitation")
    _assert_shape(first_rel, "NbReference")
    _assert_inline_shape(todos, "extractNoteTodos")
    first_todo, first_made, first_method = todos["items"][0], made[0], methods[0]
    _assert_shape(first_todo, "NbTodoDraft")
    _assert_shape(first_made, "WbItem")
    _assert_shape(draft, "NbMethodDraft")
    for payload in (method, first_method, renamed):
        _assert_shape(payload, "NbMethod")
    _assert_shape(applied, "WbItemDetail")
    _assert_shape(breakdown, "WbBreakdown")
    _assert_shape(exported, "NbExport")
