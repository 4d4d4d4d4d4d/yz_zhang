"""OPC-100~109 一人公司：财税与合规（124 号 spec）。

用户原话：「对于平台来说需要能够切实服务好每个用户的需求，满足用户的痛点，
例如 OPC 用户就需要解决繁琐的财务，政策合规申请，法务等……这些都需要 AI 来帮助实现。」
"""
import json
from datetime import date, datetime

from app.core.db import SessionLocal
from app.modules.account.models import User
from app.modules.opc import service as svc
from app.modules.opc.models import OpcEntry, OpcProfile
from app.modules.packs import schema
from app.modules.packs import service as psvc
from app.modules.tax.models import TaxWithholding
from app.modules.wallet.models import LedgerEntry
from tests.conftest import auth, make_admin

API = "/api/v1/opc"
OPC_SEED = json.loads((psvc.SEEDS / "opc-finance-compliance.json").read_text(encoding="utf-8"))


def _entry(client, user, **kw):
    body = {"occurred_on": "2026-08-10", "kind": "income", "amount_cents": 100000, **kw}
    r = client.post(f"{API}/entries", json=body, headers=auth(user))
    assert r.status_code == 201, r.text
    return r.json()


# ------------------------------------------------------------------ 主体设置
def test_profile_defaults_and_mismatch(client, requester):
    h = auth(requester)
    p = client.get(f"{API}/profile", headers=h).json()
    assert p == {"entity": "individual", "vat": "none", "vat_period": "quarter", "small_low_profit": True, "configured": False}
    r = client.put(f"{API}/profile", json={"entity": "individual", "vat": "small_scale"}, headers=h)
    assert r.status_code == 400 and r.json()["detail"]["code"] == "opc_profile_mismatch"
    r = client.put(f"{API}/profile", json={"entity": "sole_prop", "vat": "small_scale", "vat_period": "quarter"}, headers=h)
    assert r.json()["configured"] and r.json()["entity"] == "sole_prop"


# ------------------------------------------------------------------ 账本与平台收入导入（OPC-101 / 102）
def test_entries_crud_validation_and_privacy(client, requester, worker):
    h = auth(requester)
    e = _entry(client, requester, category="设计费", counterparty="甲公司", invoice_no="2026001")
    assert e["source"] == "manual" and e["amount_cents"] == 100000
    r = client.post(f"{API}/entries", json={"occurred_on": "2026-08-10", "kind": "expense", "amount_cents": 100, "tax_cents": 200}, headers=h)
    assert r.json()["detail"]["code"] == "opc_tax_exceeds_amount"
    assert client.post(f"{API}/entries", json={"occurred_on": "2026-08-10", "kind": "income", "amount_cents": 0}, headers=h).status_code == 422
    p = client.patch(f"{API}/entries/{e['id']}", json={"note": "八月设计费"}, headers=h).json()
    assert p["note"] == "八月设计费"
    for method, body in (("patch", {"note": "x"}), ("delete", None)):
        r = getattr(client, method)(f"{API}/entries/{e['id']}", headers=auth(worker), **({"json": body} if body else {}))
        assert r.status_code == 404
    assert client.get(f"{API}/entries", headers=auth(worker)).json() == []
    assert [x["id"] for x in client.get(f"{API}/entries", params={"period": "2026-Q3"}, headers=h).json()] == [e["id"]]
    assert client.get(f"{API}/entries", params={"period": "2026-Q2"}, headers=h).json() == []
    assert client.get(f"{API}/entries", params={"period": "2026-13"}, headers=h).json()["detail"]["code"] == "opc_bad_period"
    assert client.delete(f"{API}/entries/{e['id']}", headers=h).json() == {"deleted": True}


def test_import_platform_income_is_idempotent_and_locked(client, requester, worker):
    uid = requester["id"]
    with SessionLocal() as db:
        db.add(LedgerEntry(user_id=uid, kind="escrow_release", amount_cents=92000, contract_id=7, memo="任务验收放款",
                           created_at=datetime(2026, 8, 20, 3, 0)))
        db.add(LedgerEntry(user_id=uid, kind="topup", amount_cents=50000, memo="充值", created_at=datetime(2026, 8, 21)))
        db.add(LedgerEntry(user_id=uid, kind="escrow_hold", amount_cents=-30000, contract_id=8, created_at=datetime(2026, 8, 22)))
        db.add(LedgerEntry(user_id=worker["id"], kind="escrow_release", amount_cents=1, contract_id=9))
        db.commit()
    h = auth(requester)
    assert client.post(f"{API}/entries/import-platform", json={}, headers=h).json() == {"imported": 1}
    assert client.post(f"{API}/entries/import-platform", json={}, headers=h).json() == {"imported": 0}
    rows = client.get(f"{API}/entries", headers=h).json()
    assert len(rows) == 1 and rows[0]["source"] == "platform" and rows[0]["amount_cents"] == 92000
    assert rows[0]["occurred_on"] == "2026-08-20" and "已扣平台服务费" in rows[0]["note"]
    r = client.patch(f"{API}/entries/{rows[0]['id']}", json={"amount_cents": 1}, headers=h)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "opc_platform_entry_locked"
    assert client.patch(f"{API}/entries/{rows[0]['id']}", json={"invoice_no": "P-1"}, headers=h).json()["invoice_no"] == "P-1"


# ------------------------------------------------------------------ 汇总与免税标准（OPC-103）
def test_parse_period_units():
    assert svc.parse_period("2026-10") == (date(2026, 10, 1), date(2026, 10, 31), "month")
    assert svc.parse_period("2026-Q1") == (date(2026, 1, 1), date(2026, 3, 31), "quarter")
    assert svc.parse_period("2028-02")[1] == date(2028, 2, 29)
    assert svc.parse_period("2026") == (date(2026, 1, 1), date(2026, 12, 31), "year")
    assert svc.current_quarter(date(2026, 10, 13)) == "2026-Q4"
    for bad in ("2026-13", "2026-Q5", "26-01", "abc"):
        try:
            svc.parse_period(bad)
            raise AssertionError(bad)
        except ValueError:
            pass


def test_summary_vat_threshold_and_notes(client, requester):
    h = auth(requester)
    client.put(f"{API}/profile", json={"entity": "sole_prop", "vat": "small_scale", "vat_period": "quarter"}, headers=h)
    _entry(client, requester, amount_cents=200_000_00, category="设计费")
    _entry(client, requester, occurred_on="2026-09-01", amount_cents=99_999_00, category="设计费")
    _entry(client, requester, kind="expense", amount_cents=5000_00, category="软件订阅")
    with SessionLocal() as db:
        db.add(TaxWithholding(user_id=requester["id"], contract_id=1, income_cents=1, taxable_cents=1, withheld_cents=1234,
                              created_at=datetime(2026, 8, 30)))
        db.commit()
    s = client.get(f"{API}/summary", params={"period": "2026-Q3"}, headers=h).json()
    assert s["income_cents"] == 299_999_00 and s["expense_cents"] == 5000_00 and s["profit_cents"] == 294_999_00
    assert s["vat_check"] == {"period_kind": "quarter", "sales_cents": 299_999_00, "limit_cents": 300_000_00, "over": False}
    assert "未超过免税标准" in s["notes"][0] and "2023年第19号" in s["notes"][0] and "2027-12-31" in s["notes"][0]
    assert any("个体工商户" in n and "200 万" in n for n in s["notes"])
    assert any("1 笔支出没有记发票号" in n for n in s["notes"])
    assert s["platform_withheld_cents"] == 1234 and "不是申报表" in s["disclaimer"]
    _entry(client, requester, occurred_on="2026-09-30", amount_cents=200)
    over = client.get(f"{API}/summary", params={"period": "2026-Q3"}, headers=h).json()
    assert over["vat_check"]["over"] and "减按 1%" in over["notes"][0]
    # 按季申报的人看月度汇总：提示选季度，不给错误口径的结论
    month = client.get(f"{API}/summary", params={"period": "2026-08"}, headers=h).json()
    assert month["vat_check"] is None and "季度" in month["notes"][0]


def test_policy_note_says_when_it_may_have_changed():
    assert "执行至 2027-12-31" in svc.policy_note("vat_small", date(2026, 10, 13))
    assert "已过期，政策可能已变" in svc.policy_note("vat_small", date(2028, 1, 1))


def test_csv_export(client, requester):
    h = auth(requester)
    _entry(client, requester, category="设计费", counterparty="甲公司", invoice_no="2026001", invoice_kind="ordinary")
    out = client.get(f"{API}/export", params={"period": "2026-08"}, headers=h).json()
    assert out["filename"] == "opc-2026-08.csv" and out["rows"] == 1
    lines = out["csv"].strip().splitlines()
    assert lines[0].startswith("日期,收支,含税金额（元）") and lines[1] == "2026-08-10,收入,1000.00,0.00,设计费,甲公司,2026001,普通发票,手记,"


# ------------------------------------------------------------------ 申报日历（OPC-104）
def test_calendar_units():
    today = date(2026, 10, 13)
    small_q = OpcProfile(entity="sole_prop", vat="small_scale", vat_period="quarter")
    items = svc.deadlines(small_q, today, 120)
    titles = [(i["date"], i["title"]) for i in items]
    assert ("2026-10-15", "申报上季度增值税及附加税费") in titles
    assert ("2026-10-15", "预缴上季度经营所得个人所得税") in titles
    assert ("2027-01-15", "申报上季度增值税及附加税费") in titles
    assert not any(d.startswith("2026-11") for d, _ in titles)        # 按季：11 月不申报
    monthly = svc.deadlines(OpcProfile(entity="company", vat="small_scale", vat_period="month"), today, 60)
    # 按月申报每月都有；2026-11-15 是周日 → 顺延到周一 11-16
    assert {i["date"] for i in monthly if i["kind"] == "vat"} == {"2026-10-15", "2026-11-16"}
    company = svc.deadlines(OpcProfile(entity="company", vat="general", vat_period="month"), date(2027, 1, 1), 200)
    kinds = {(i["date"], i["kind"]) for i in company}
    assert ("2027-05-31", "cit") in kinds and ("2027-06-30", "annual") in kinds
    individual = svc.deadlines(OpcProfile(entity="individual", vat="none", vat_period="quarter"), date(2027, 1, 1), 200)
    assert [i["title"] for i in individual] == ["综合所得个人所得税年度汇算截止"]


def test_calendar_endpoint(client, requester):
    h = auth(requester)
    r = client.get(f"{API}/calendar", headers=h).json()
    assert r["configured"] is False and "以电子税务局为准" in r["notice"]
    client.put(f"{API}/profile", json={"entity": "company", "vat": "small_scale", "vat_period": "quarter"}, headers=h)
    assert client.get(f"{API}/calendar", params={"days": 400}, headers=h).json()["configured"] is True


# ------------------------------------------------------------------ 合同体检（OPC-105）
CONTRACT = """服务合同
甲方委托乙方完成品牌设计，总价人民币 50000 元，2026年11月30日前交付。
乙方完成的全部成果，其著作权归甲方所有。
如乙方违约，应支付合同总额 50% 的违约金，并承担甲方的一切损失。
本合同自动续约，甲方保留最终解释权。定金为合同总额的 30%。
"""


def test_contract_review_flags_and_disclaims(client, requester):
    r = client.post(f"{API}/contract-review", json={"text": CONTRACT, "role": "party_b"}, headers=auth(requester)).json()
    by_clause = {f["clause"]: f for f in r["findings"]}
    assert "验收标准与期限" in by_clause and by_clause["验收标准与期限"]["level"] == "high"
    assert "争议解决（协商 / 仲裁 / 管辖法院）" in by_clause
    assert by_clause["知识产权"]["level"] == "high" and "付清" in by_clause["知识产权"]["suggestion"]
    assert "第五百八十五条" in by_clause["违约金"]["suggestion"]
    assert "第五百八十六条" in by_clause["定金"]["suggestion"]
    assert {"责任上限", "续约", "解释权"} <= set(by_clause)
    assert r["findings"][0]["level"] == "high" and "不构成法律意见" in r["disclaimer"]
    assert "50000" in r["amounts"] and "2026年11月30日" in r["dates"]
    # 甲方视角：权利归自己，不提示
    a = client.post(f"{API}/contract-review", json={"text": CONTRACT, "role": "party_a"}, headers=auth(requester)).json()
    assert "知识产权" not in {f["clause"] for f in a["findings"]}
    # 写了付清后转移：乙方也不再提示
    ok = CONTRACT.replace("其著作权归甲方所有", "在甲方付清全部款项后，其著作权归甲方所有")
    b = client.post(f"{API}/contract-review", json={"text": ok, "role": "party_b"}, headers=auth(requester)).json()
    assert "知识产权" not in {f["clause"] for f in b["findings"]}


# ------------------------------------------------------------------ OPC 服务包（V149）
def test_opc_seed_is_valid_and_high_risk_gated():
    d, problems = schema.validate(OPC_SEED)
    assert d is not None and not problems, problems
    for a in d.assistants:
        assert {"money", "sign", "file"} <= set(a.human_gates)
    assert all(k.valid_until for k in d.knowledge if k.kind == "policy")


def _publish_opc(client):
    a, b = make_admin(client, "13900000201", "运营甲"), make_admin(client, "13900000202", "运营乙")
    pid = client.post("/api/v1/admin/packs", json={"definition": OPC_SEED}, headers=auth(a)).json()["id"]
    client.post(f"/api/v1/admin/packs/{pid}/submit", headers=auth(a))
    r = client.post(f"/api/v1/admin/packs/{pid}/approve", headers=auth(b))
    assert r.status_code == 200, r.text
    return a, b


def test_approve_refuses_unknown_categories(client):
    a, b = make_admin(client, "13900000211", "运营甲"), make_admin(client, "13900000212", "运营乙")
    bad = {**OPC_SEED, "key": "opc-x", "task_templates": [{**OPC_SEED["task_templates"][0], "category": "不存在的类目"}]}
    pid = client.post("/api/v1/admin/packs", json={"definition": bad}, headers=auth(a)).json()["id"]
    client.post(f"/api/v1/admin/packs/{pid}/submit", headers=auth(a))
    r = client.post(f"/api/v1/admin/packs/{pid}/approve", headers=auth(b))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "pack_unknown_category" and "不存在的类目" in r.json()["detail"]["message"]


def test_opc_assistants_use_my_own_books_and_calendar(client, requester):
    _publish_opc(client)
    h = auth(requester)
    client.put(f"{API}/profile", json={"entity": "sole_prop", "vat": "small_scale", "vat_period": "quarter"}, headers=h)
    ask = "/api/v1/packs/opc-finance-compliance/assistants/tax-assistant/ask"
    r = client.post(ask, json={"q": "小规模纳税人季度免税标准是多少，什么时候申报"}, headers=h).json()
    kinds = [c["kind"] for c in r["citations"]]
    assert "pack" in kinds and "tool" in kinds
    tool = next(c for c in r["citations"] if c["title"].startswith("你的申报日历"))
    assert "申报上季度增值税" in tool["snippet"] or "预缴" in tool["snippet"]
    assert any("2023年第19号" in c["source"] for c in r["citations"] if c["kind"] == "pack")
    assert set(r["gates"]) >= {schema.GATES["money"], schema.GATES["file"], schema.GATES["sign"]}
    books = client.post(ask, json={"q": "我这季度收入多少"}, headers=h).json()
    assert any(c["title"].startswith("你的记账底稿") for c in books["citations"])
    contract = client.post("/api/v1/packs/opc-finance-compliance/assistants/contract-assistant/ask",
                           json={"q": "帮我看下这份合同：" + CONTRACT}, headers=h).json()
    assert any(c["title"] == "合同体检（按条款清单）" for c in contract["citations"])
    # 别人的数据不会出现：worker 没有账，问「收入」得到的是 0
    with SessionLocal() as db:
        assert db.query(OpcEntry).count() == 0


def test_enable_opc_pack_installs_routines_and_templates_point_to_live_category(client, requester):
    _publish_opc(client)
    h = auth(requester)
    r = client.post("/api/v1/packs/opc-finance-compliance/enable", json={}, headers=h).json()
    assert r["installed"] == {"methods": 4, "notes": 13, "routines": 2}
    cats = {c["name"] for c in client.get("/api/v1/categories").json()}
    assert "财税" in cats and all(t["category"] in cats for t in r["assets"]["task_templates"])


# ------------------------------------------------------------------ 注销与导出（OPC-109）
def test_erase_and_export(client, requester):
    from app.modules.account.deletion import erase_personal_data

    h = auth(requester)
    client.put(f"{API}/profile", json={"entity": "company", "vat": "general"}, headers=h)
    _entry(client, requester, counterparty="甲公司")
    full = client.get("/api/v1/users/me/export", headers=h).json()
    assert full["opc"]["profile"]["entity"] == "company" and full["opc"]["entries"][0]["counterparty"] == "甲公司"
    with SessionLocal() as db:
        erase_personal_data(db, db.get(User, requester["id"]))
        db.commit()
        assert db.query(OpcEntry).count() == 0 and db.get(OpcProfile, requester["id"]) is None


# ------------------------------------------------------------------ 响应形状（CLI-083）
def test_responses_match_sdk_types(client, requester):
    from tests.test_client_shape_alignment import _assert_inline_shape, _assert_shape

    h = auth(requester)
    profile = client.put(f"{API}/profile", json={"entity": "sole_prop", "vat": "small_scale"}, headers=h).json()
    got_profile = client.get(f"{API}/profile", headers=h).json()
    created = _entry(client, requester, kind="expense", category="软件订阅")
    patched = client.patch(f"{API}/entries/{created['id']}", json={"note": "n"}, headers=h).json()
    listed = client.get(f"{API}/entries", headers=h).json()
    imported = client.post(f"{API}/entries/import-platform", json={}, headers=h).json()
    summary = client.get(f"{API}/summary", params={"period": "2026-Q3"}, headers=h).json()
    exported = client.get(f"{API}/export", params={"period": "2026-08"}, headers=h).json()
    cal = client.get(f"{API}/calendar", params={"days": 400}, headers=h).json()
    review = client.post(f"{API}/contract-review", json={"text": CONTRACT}, headers=h).json()
    for p in (profile, got_profile):
        _assert_shape(p, "OpcProfileView")
    for e in (created, patched):
        _assert_shape(e, "OpcEntryRow")
    first_listed, first_cat, vat, first_item, first_finding = (
        listed[0], summary["by_category"][0], summary["vat_check"], cal["items"][0], review["findings"][0])
    _assert_shape(first_listed, "OpcEntryRow")
    _assert_inline_shape(imported, "importPlatformIncome")
    _assert_shape(summary, "OpcSummary")
    _assert_shape(first_cat, "OpcCategoryTotal")
    _assert_shape(vat, "OpcVatCheck")
    _assert_shape(exported, "OpcExport")
    _assert_shape(cal, "OpcCalendar")
    _assert_shape(first_item, "OpcDeadline")
    _assert_shape(review, "ContractReview")
    _assert_shape(first_finding, "ContractFinding")


def test_calendar_tool_window_always_reaches_the_next_quarterly_deadline():
    """10-16 起，按季申报的下一个节点是次年 1-15：只看 90 天就一条都没有（真出过：日期一过 10-15 测试就红）。
    每一天都要看得到下一次申报——逐日扫一整年。"""
    from datetime import date, timedelta

    from app.modules.opc import service as osvc
    from app.modules.opc.models import OpcProfile
    from app.modules.packs.service import CALENDAR_DAYS

    for entity, vat in (("sole_prop", "small_scale"), ("company", "small_scale"), ("individual", "small_scale")):
        p = OpcProfile(user_id=1, entity=entity, vat=vat, vat_period="quarter")
        d = date(2026, 1, 1)
        while d < date(2027, 1, 1):
            assert osvc.deadlines(p, d, CALENDAR_DAYS), (entity, d)
            d += timedelta(days=1)
