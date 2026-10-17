"""IPC 知识产权与保密条款 + OUT 浮动对价（52 号 spec）。

IPC 的起点是一条实测出来的缺陷：合同模板有金额、验收、争议、性质声明四段，
**没有知识产权归属，也没有保密条款**。

按《著作权法》第十七条，委托作品无约定时著作权归**受托人**——
也就是说发布方花 ¥3000 买的那套 logo，默认不属于他。
而 `软件开发` 类目的发布模板里还写着 checklist「约定源码归属」：
平台自己提示用户去约定，然后没有提供任何约定的地方。
"""
from app.core.db import SessionLocal
from app.modules.contract.clauses import IP_ASSIGNMENTS
from tests.conftest import auth, register, topup, verify_user
from tests.test_task_flow import CLEAN_TASK, match_and_fund, publish_task


def publish(client, user, **over):
    body = {**CLEAN_TASK, "ip_assignment": "assign", **over}
    return client.post("/api/v1/tasks", json=body, headers=auth(user))


def outcome_task(client, requester, **over):
    """一个合法的 outcome 计价任务。"""
    return publish(client, requester, pricing="outcome", budget_cents=20000,
                   bonus_cents=5000, acceptance_criteria=[
                       {"text": "交付说明须包含「已通过自测」", "kind": "auto",
                        "check": {"op": "contains", "value": "已通过自测"}},
                   ], **over)


# --------------------------------------------------------- IPC-001 归属必须选
def test_ipc001_publishing_without_choosing_ip_assignment_is_rejected(client, requester):
    """**没有默认值是有意的。**

    最容易犯的错是「默认归发布方」——那对执行方不公平，
    而且对通用组件、含第三方素材的交付物直接就是错的。
    """
    body = {**CLEAN_TASK}
    body.pop("ip_assignment", None)
    r = client.post("/api/v1/tasks", json=body, headers=auth(requester))
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "ip_assignment_required"
    # 理由要说清楚不选的后果，否则用户只会随便选一个
    assert "著作权" in r.json()["detail"]["message"]


def test_ipc001_all_four_assignments_are_accepted(client, requester):
    for i, kind in enumerate(IP_ASSIGNMENTS):
        r = publish(client, requester, ip_assignment=kind, title=f"任务{i}")
        assert r.status_code == 201, (kind, r.text)


def test_ipc001_unknown_assignment_is_rejected(client, requester):
    r = publish(client, requester, ip_assignment="whatever_i_want")
    assert r.status_code == 400


# ------------------------------------------------ IPC-001~003 条款真的写进合同
def _contract_terms(client, requester, worker, **over):
    topup(client, requester, 200000)
    topup(client, worker, 50000)
    task = publish(client, requester, **over).json()
    cid = match_and_fund(client, requester, worker, task)
    return client.get(f"/api/v1/contracts/{cid}", headers=auth(requester)).json()["terms"]


def test_ipc001_assignment_clause_matches_the_chosen_option(client, requester, worker):
    terms = _contract_terms(client, requester, worker, ip_assignment="assign")
    assert "著作财产权" in terms and "转让给发布方" in terms


def test_ipc003_moral_rights_are_not_claimed_to_be_transferable(client, requester, worker):
    """**把「著作权全部转让」写进合同是一句无效的话**，
    而写无效的话比不写更糟：当事人会以为自己拿到了实际上没有的东西。"""
    terms = _contract_terms(client, requester, worker, ip_assignment="assign")
    assert "署名权" in terms and "不得转让" in terms
    assert "著作权全部转让" not in terms


def test_ipc001_retain_option_says_the_opposite_thing(client, requester, worker):
    terms = _contract_terms(client, requester, worker, ip_assignment="retain")
    assert "著作权归执行方所有" in terms
    assert "转让给发布方" not in terms


def test_ipc002_confidentiality_is_mutual(client, requester, worker):
    """**只约束一方的保密条款在谈判上站不住，在履行上也不公平。**"""
    terms = _contract_terms(client, requester, worker)
    assert "保密:" in terms
    assert "发布方侧" in terms and "执行方侧" in terms
    # 例外情形要写，否则「已经公开的信息」也成了违约
    assert "已公开" in terms and "独立开发" in terms


def test_ipc050_template_does_not_pretend_to_be_a_lawyer(client, requester, worker):
    terms = _contract_terms(client, requester, worker)
    assert "平台模板生成" in terms and "执业律师" in terms


def test_ipc004_changing_the_task_does_not_change_a_signed_contract(client, requester, worker):
    """归属随**已签署的那一版**走。

    不这样做就有个洞：事后改一下任务字段，等于单方面改了归属。
    """
    from app.modules.task.models import Task

    topup(client, requester, 200000)
    topup(client, worker, 50000)
    task = publish(client, requester, ip_assignment="assign").json()
    cid = match_and_fund(client, requester, worker, task)
    with SessionLocal() as db:                      # 偷偷改任务字段
        db.get(Task, task["id"]).ip_assignment = "retain"
        db.commit()
    terms = client.get(f"/api/v1/contracts/{cid}", headers=auth(requester)).json()["terms"]
    assert "转让给发布方" in terms, "改任务字段就改掉了已签合同的归属"


# ------------------------------------------------------- OUT-001/002 发布校验
def test_out001_outcome_pricing_requires_criteria(client, requester):
    """**没有判据的「做得好多给钱」是一句无法执行的承诺。**"""
    r = publish(client, requester, pricing="outcome", bonus_cents=5000,
                acceptance_criteria=[])
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "criteria_required_for_outcome"


def test_out001_outcome_pricing_requires_at_least_one_objective_criterion(client, requester):
    """全是人工确认的话，达标与否完全由发布方说了算。"""
    r = publish(client, requester, pricing="outcome", bonus_cents=5000,
                acceptance_criteria=[{"text": "整体感觉不错", "kind": "manual"}])
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "auto_criterion_required"


def test_out002_bonus_must_be_a_capped_positive_amount(client, requester):
    """**有确定上限的附加对价是价款，随收益浮动的比例是分配**——
    封顶是把两者分开的关键。"""
    r = publish(client, requester, pricing="outcome", bonus_cents=0,
                acceptance_criteria=[{"text": "x", "kind": "auto",
                                      "check": {"op": "min_length", "value": 1}}])
    assert r.status_code == 400 and r.json()["detail"]["code"] == "bonus_required"

    r = publish(client, requester, pricing="outcome", budget_cents=10000,
                bonus_cents=50000,
                acceptance_criteria=[{"text": "x", "kind": "auto",
                                      "check": {"op": "min_length", "value": 1}}])
    assert r.status_code == 400 and r.json()["detail"]["code"] == "bonus_too_large"


def test_bonus_not_allowed_on_other_pricing_modes(client, requester):
    r = publish(client, requester, pricing="fixed", bonus_cents=1000)
    assert r.status_code == 400 and r.json()["detail"]["code"] == "bonus_not_allowed"


def test_finance_redline_still_blocks_revenue_sharing(client, requester):
    """**那条红线不动。** outcome 是与交付成果挂钩，不是与收益挂钩。"""
    r = publish(client, requester, pricing="outcome", budget_cents=20000,
                bonus_cents=5000, description="按下载量给分红，年化收益率可观",
                acceptance_criteria=[{"text": "x", "kind": "auto",
                                      "check": {"op": "min_length", "value": 1}}])
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "finance_offer_forbidden"


# ------------------------------------------------------- OUT-003/004 托管与判定
def test_out003_bonus_is_escrowed_upfront(client, requester, worker):
    """**不托管的话，「做得好多给钱」就变成了一句口头承诺**——
    执行方把活干到了约定水平，发布方不给，平台没有任何东西可以执行。"""
    topup(client, requester, 200000)
    topup(client, worker, 50000)
    task = outcome_task(client, requester).json()
    cid = match_and_fund(client, requester, worker, task)
    c = client.get(f"/api/v1/contracts/{cid}", headers=auth(requester)).json()
    assert c["amount_cents"] == 25000, "托管额应为 基础 20000 + 浮动 5000"
    w = client.get("/api/v1/wallet", headers=auth(requester)).json()
    assert w["escrow_cents"] == 25000


def test_out004_bonus_is_paid_when_the_platform_criteria_pass(client, requester, worker):
    topup(client, requester, 200000)
    topup(client, worker, 50000)
    task = outcome_task(client, requester).json()
    match_and_fund(client, requester, worker, task)
    # 交付说明命中 auto 判据
    client.post(f"/api/v1/tasks/{task['id']}/deliver",
                json={"note": "功能已完成，已通过自测"}, headers=auth(worker))
    before = client.get("/api/v1/wallet", headers=auth(worker)).json()["available_cents"]
    client.post(f"/api/v1/tasks/{task['id']}/accept-delivery", headers=auth(requester))
    after = client.get("/api/v1/wallet", headers=auth(worker)).json()["available_cents"]
    # 25000 扣佣金后到账；关键是它**明显高于**只放基础报酬的情形
    assert after - before > 20000 * 0.9, f"浮动部分没付：{after - before}"


def test_out004_bonus_is_refunded_when_criteria_fail(client, requester, worker):
    """没达标的原路退回发布方——而且资金必须守恒。"""
    topup(client, requester, 200000)
    topup(client, worker, 50000)
    task = outcome_task(client, requester).json()
    match_and_fund(client, requester, worker, task)
    client.post(f"/api/v1/tasks/{task['id']}/deliver",
                json={"note": "做完了"}, headers=auth(worker))   # 不含判据要求的字样

    r_before = client.get("/api/v1/wallet", headers=auth(requester)).json()
    w_before = client.get("/api/v1/wallet", headers=auth(worker)).json()["available_cents"]
    client.post(f"/api/v1/tasks/{task['id']}/accept-delivery", headers=auth(requester))
    r_after = client.get("/api/v1/wallet", headers=auth(requester)).json()
    w_after = client.get("/api/v1/wallet", headers=auth(worker)).json()["available_cents"]

    assert r_after["available_cents"] - r_before["available_cents"] == 5000, "浮动没退回"
    assert r_after["escrow_cents"] == 0
    assert w_after - w_before < 20000, "没达标却付了浮动部分"


def test_out004_money_is_conserved_either_way(client, requester, worker):
    from tests.conftest import make_admin

    admin = make_admin(client, "13400000001")
    topup(client, requester, 200000)
    topup(client, worker, 50000)
    for hit, title in ((True, "达标单"), (False, "未达标单")):
        task = outcome_task(client, requester, title=title).json()
        match_and_fund(client, requester, worker, task)
        client.post(f"/api/v1/tasks/{task['id']}/deliver",
                    json={"note": "已通过自测" if hit else "做完了"},
                    headers=auth(worker))
        client.post(f"/api/v1/tasks/{task['id']}/accept-delivery", headers=auth(requester))
    rec = client.post("/api/v1/admin/jobs/reconcile", headers=auth(admin)).json()
    assert rec["ok"] is True, rec["mismatches"]


def test_out_terms_state_the_cap_the_criteria_and_who_judges(client, requester, worker):
    """条款必须写清楚三件事，否则它就是一句口头承诺。"""
    topup(client, requester, 200000)
    topup(client, worker, 50000)
    task = outcome_task(client, requester).json()
    cid = match_and_fund(client, requester, worker, task)
    terms = client.get(f"/api/v1/contracts/{cid}", headers=auth(requester)).json()["terms"]
    assert "浮动对价" in terms
    assert "上限即此数" in terms and "不随任何收益浮动" in terms
    assert "平台判定" in terms
    assert "原路退回发布方" in terms


# ------------------------- 建好了却没接上：这一批自己差点犯的那个错
def test_web_publish_form_can_satisfy_the_new_server_requirement():
    """**服务端加了必填项，客户端没跟上 = 发布功能整个不可用。**

    这是 V59（人机验证服务端门没有客户端能满足）、V61（纠纷端点无入口）、
    V64（media_urls 从没传下去）反复出现的同一个形状，
    而这一批加 `ip_assignment` 必填时我自己也差一点犯。

    钉三处：SDK 类型里有、Web 表单 state 里有、提交时真的传了。
    """
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[2]
    types_ts = (root / "packages/core/src/types.ts").read_text(encoding="utf-8")
    publish_tsx = (root / "web/src/pages/Publish.tsx").read_text(encoding="utf-8")

    def code(src: str) -> str:
        return "\n".join(line.split("//")[0] for line in src.splitlines())

    assert "ip_assignment" in code(types_ts), "SDK 类型里没有 ip_assignment"
    body = code(publish_tsx)
    assert "ip_assignment: form.ip_assignment" in body, "发布表单没把 ip_assignment 传给服务端"
    assert "IP_ASSIGNMENT_LABEL" in body, "表单里没有让用户选归属的控件"


def test_every_ip_option_the_server_accepts_has_a_client_label():
    """双向对齐：服务端认的档位，客户端都要有中文名，反之亦然。

    与 SYNC-002（账本科目 ↔ SDK 文案）同一条规矩——
    少一个的后果是用户在下拉框里选不到某个合法选项，而没有任何东西会报错。
    """
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parents[2]
    types_ts = (root / "packages/core/src/types.ts").read_text(encoding="utf-8")
    block = re.search(
        r"export const IP_ASSIGNMENT_LABEL: Record<IpAssignment, string> = \{(.*?)\n\};",
        types_ts, re.S,
    )
    assert block, "没找到 IP_ASSIGNMENT_LABEL——正则失配时必须失败，不能返回空集"
    labels = set(re.findall(r"^\s*([a-z_]+):", block.group(1), re.M))
    assert len(labels) >= 4, f"只解析出 {len(labels)} 条，正则多半失配了"
    assert labels == set(IP_ASSIGNMENTS), (
        f"服务端 {sorted(IP_ASSIGNMENTS)} 与客户端 {sorted(labels)} 不一致"
    )
