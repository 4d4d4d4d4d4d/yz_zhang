"""KB-060 经验数据的脱敏（83 号 spec）。

探针（V108）：两处经验管线的 docstring 都写着「脱敏」，两处都存着用户原文。

    KnowledgeCard 的 docstring：「闭环任务经验卡（脱敏后的结构化经验）」
    落库的 title：给王芳家搬钢琴 朝阳区幸福小区3号楼502 联系13800138000
    别的用户读经验卡：200，能读到含手机号的卡：True

    _record_lesson 的 docstring：「脱敏：不写 user_id、不写精确地址、不写金额」
    拼出来的系统提示词：含手机号 True、含姓名 True、含地址 True

一个客户的电话与门牌号，(a) 通过经验卡端点给了**别的用户**，
(b) 通过提示词给了**第三方模型**。这不是数据质量问题，是《个人信息保护法》
的最小必要与目的限制——**写在注释里的「脱敏」，没有任何东西在做。**
"""
from app.core.db import SessionLocal
from app.core.scrub import MASK, scrub_text
from tests.conftest import auth, register, topup, verify_user
from tests.test_task_flow import match_and_fund, publish_task

DIRTY = "给王芳家搬钢琴 朝阳区幸福小区3号楼502 联系13800138000"


# ------------------------------------------------- 脱敏函数本身
def test_kb060_numbers_are_removed_not_partially_masked():
    """经验数据里数字要**整段抹掉**，不是日志那种保留头尾的掩码。

    日志里 `138****8000` 是对的——运维要靠头尾把几条日志对上。
    而经验数据的去处是别的用户与第三方模型，**末四位加城市常常足够定位到人**。
    """
    out = scrub_text("联系13800138000 或 zhang@example.com")
    assert "13800138000" not in out
    assert "8000" not in out, "保留了末四位——在这个用途上那不是折中，是漏"
    assert "zhang@example.com" not in out
    assert MASK in out


def test_kb060_precise_location_goes_but_the_district_stays():
    """门牌与小区抹掉，**行政区留着**。

    价格与工期随地段变，区是经验里有用的部分；精确到一个小区、一户人家就不是了。
    """
    out = scrub_text("朝阳区幸福小区3号楼502")
    assert "朝阳区" in out, "行政区被抹了——那把经验里有用的部分也扔了"
    assert "幸福小区" not in out
    assert "3号楼" not in out


def test_kb060_party_names_are_removed_by_lookup_not_by_guessing():
    """姓名靠**平台已知的当事人姓名**去替换，不写「中文姓名识别」。

    那种识别会把「王府井」「张江」当成人名，而平台本来就知道这一单是谁和谁。
    """
    out = scrub_text("王芳确认过现场", ("王芳",))
    assert "王芳" not in out
    # 反面：不许把地名当人名
    assert "王府井" in scrub_text("在王府井附近", ("王芳",))


def test_kb060_no_false_positives_on_money_and_cities():
    """假报警多的脱敏会把经验洗成没用的东西。"""
    text = "上海市浦东新区的保洁任务，预算 500 元，耗时 3 天"
    assert scrub_text(text) == text


def test_kb060_boundary_is_documented_third_party_names_cannot_be_caught():
    """**这条闸门守不住什么，也要写下来。**

    核验人自己打的字里出现第三方姓名（「客户李强投诉」），正则认不出来——
    平台不知道「李强」是谁。所以这一批的保证是有边界的：
    机器能认的（号码、邮箱、门牌、小区、当事人姓名）一定去掉，
    任意第三方姓名**去不掉**。

    把这条写成测试，是为了**不让下一个人以为这里已经完全匿名化了**——
    那种误解比漏本身更危险（它会让人放心地把这段文本送到更多地方去）。
    """
    out = scrub_text("客户李强投诉未按时到")
    assert "李强" in out, (
        "如果这条断言开始失败，说明有人加了姓名识别——"
        "那是好事，但要同时更新 83 号 spec 里「守不住什么」那一节"
    )


# ------------------------------------------------- 写入点：经验卡
def test_kb060_knowledge_card_stores_no_free_text(client, requester):
    """最可靠的脱敏是**不采集**：这张卡的用途是按类目/城市看价格与工期，
    用户打的标题对它没有必要，而它是这条链上唯一的自由文本。"""
    worker = register(client, "13800170001", "执行者")
    verify_user(client, worker, name="执行")
    topup(client, requester, 200000)
    task = publish_task(client, requester, title=DIRTY)
    match_and_fund(client, requester, worker, task)
    client.post(f"/api/v1/tasks/{task['id']}/deliver", headers=auth(worker))
    client.post(f"/api/v1/tasks/{task['id']}/accept-delivery", headers=auth(requester))

    with SessionLocal() as db:
        from app.modules.knowledge.models import KnowledgeCard

        card = db.query(KnowledgeCard).order_by(KnowledgeCard.id.desc()).first()
        assert card is not None, "闭环了却没生成经验卡"
        for leak in ("13800138000", "王芳", "3号楼", "幸福小区"):
            assert leak not in card.title, f"经验卡里还有 {leak}"
        # 卡还是有用的：类目与城市在
        assert task["category"] in card.title
        assert card.price_actual_cents > 0 and card.duration_days >= 0


def test_kb060_other_users_cannot_read_personal_text_from_cards(client, requester):
    """这张卡是给**别人**看的——探针实测别的用户能读到含手机号的卡。"""
    worker = register(client, "13800170010", "执行者")
    verify_user(client, worker, name="执行")
    topup(client, requester, 200000)
    task = publish_task(client, requester, title=DIRTY)
    match_and_fund(client, requester, worker, task)
    client.post(f"/api/v1/tasks/{task['id']}/deliver", headers=auth(worker))
    client.post(f"/api/v1/tasks/{task['id']}/accept-delivery", headers=auth(requester))

    other = register(client, "13800170011", "路人")
    r = client.get("/api/v1/knowledge/cards", headers=auth(other))
    assert r.status_code == 200, r.text
    body = r.json()
    items = body if isinstance(body, list) else body.get("items", [])
    blob = str(items)
    for leak in ("13800138000", "王芳", "幸福小区"):
        assert leak not in blob, f"别的用户能从经验卡里读到 {leak}"


# ------------------------------------------------- 读出点：提示词
def _lesson(db, *, category="保洁", outcome="revised", **kw):
    from app.modules.verify.models import VerificationLesson

    row = VerificationLesson(category=category, outcome=outcome, criteria=[], **kw)
    db.add(row)
    return row


def test_kb060_prompt_scrubs_again_at_read_time(client):
    """库里已经有写入点修好之前落下的行——只在写入点做，那些旧行会一直被喂给模型。

    这段文本的去处是第三方模型：多一道防线的成本是一次正则，
    漏出去的成本是一条个人信息。
    """
    from app.modules.verify.models import VerificationLesson
    from app.modules.verify.service import lessons_prompt

    with SessionLocal() as db:
        _lesson(db, task_title=DIRTY[:120],
                reason="客户投诉未按约定时间到，电话13900139000，地址朝阳区幸福小区8号楼",
                revision_summary="重做并联系 13900139000 确认")
        db.commit()
        rows = db.query(VerificationLesson).all()
        prompt = lessons_prompt(rows)

    for leak in ("13900139000", "幸福小区", "8号楼"):
        assert leak not in prompt, f"提示词里还有 {leak}"
    # 任务标题整条不进提示词：类目已经限定了「同类」，标题是最脏的那一段
    assert "搬钢琴" not in prompt
    assert "同类任务" in prompt, "去掉标题之后要仍然说清这是同类任务的经验"


def test_kb060_identical_lessons_are_not_repeated_in_the_prompt(client):
    """同一条结论重复出现会把它的权重放大成「这是最重要的一条」。"""
    from app.modules.verify.models import VerificationLesson
    from app.modules.verify.service import lessons_prompt

    with SessionLocal() as db:
        for _ in range(3):
            _lesson(db, task_title="保洁", reason="没有拍完工照片", revision_summary="")
        db.commit()
        rows = db.query(VerificationLesson).all()
        prompt = lessons_prompt(rows)

    assert prompt.count("没有拍完工照片") == 1, "同一条经验被重复喂了多次"


# `runner` 是 test_orchestrator_agents 里的 fixture（把 agent 执行器换成
# 一个记录提示词的假实现）。pytest 的 fixture 不跨文件自动可见，显式导进来——
# 比在这里再写一个假执行器好：**第二份实现必然抄漏**
from tests.test_orchestrator_agents import runner  # noqa: F401,E402


def test_kb060_personal_text_never_reaches_a_real_agent_prompt(client, requester, runner):
    """最有说服力的一条：**真的跑一遍 agent**，看喂进去的提示词里有什么。

    上面那些断言拼的是 `lessons_prompt()` 的输出；这一条走的是
    V86 建的整条路（mission → 派给 agent → 组装系统提示词），
    也就是个人信息真正会流到第三方模型的那条路。

    第一版这里写的是「调一次 scrub_text 看它管用」——那不是在测写入点，
    是在测我刚写的函数。删掉换成这条。
    """
    from tests.test_orchestrator_agents import make_agent, make_mission, tick
    from tests.conftest import make_admin

    admin = make_admin(client, "13800170030")
    make_agent(client, admin, domains=["软件开发"], max_task_budget_cents=100000)
    with SessionLocal() as db:
        _lesson(db, category="软件开发", task_title=DIRTY[:120],
                reason="客户投诉未按时交付，电话13900139000，朝阳区幸福小区8号楼",
                revision_summary="联系 13900139000 重新确认")
        db.commit()

    topup(client, requester, 300000)
    m = make_mission(client, requester, allow_agents=True)
    tick(client, requester, m["id"])

    assert runner.prompts, "agent 没被执行，这条就什么也没验到"
    prompt = runner.prompts[-1]
    for leak in ("13900139000", "幸福小区", "8号楼", "搬钢琴"):
        assert leak not in prompt, f"真实提示词里漏了 {leak}"
    # 经验本身还是喂到了——脱敏不能把有用的部分一起洗掉
    assert "人工核验指出过的问题" in prompt
    assert "客户投诉未按时交付" in prompt


# ------------------------------------------------- 写入点闸门（AST）
def test_kb060_free_text_fields_must_go_through_the_scrubber():
    """经验类表的自由文本字段，赋值必须来自 `scrub_text(...)` 或派生值。

    这一条是这一批的主产出：**光修好现在这两处不够**——下一个人加一个
    `note` 字段、或者再建一张经验表，就又会原样入库。用 AST 扫构造调用，
    而不是正则：正则读不懂「这个关键字参数的值是什么表达式」。
    """
    import ast
    from pathlib import Path

    repo = Path(__file__).resolve().parents[2]
    # 表 -> 必须脱敏的字段。值是**字段名**而不是布尔：
    # 加字段的人要在这里写一行，那一行就是他想过这件事的证据
    guarded = {
        "KnowledgeCard": {"title"},
        "VerificationLesson": {"task_title", "reason", "revision_summary"},
    }
    offenders: list[str] = []
    checked = 0
    for path in sorted((repo / "server" / "app").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            fields = guarded.get(name or "")
            if not fields:
                continue
            for kw in node.keywords:
                if kw.arg not in fields:
                    continue
                checked += 1
                ok = (
                    # scrub_text(...) 或 [scrub_text(...) for ...]
                    "scrub_text" in ast.dump(kw.value)
                    # 或者是从结构化字段拼出来的（f"{category}·{city}"）——
                    # 那里面没有用户打的字
                    or isinstance(kw.value, ast.JoinedStr)
                )
                if not ok:
                    offenders.append(
                        f"{path.relative_to(repo)}:{node.lineno} {name}.{kw.arg}")
    assert checked >= 4, f"只检查了 {checked} 个字段，AST 提取可能坏了"
    assert not offenders, (
        "这些经验字段没经过脱敏就入库了（它们会流到别的用户与第三方模型）：\n  "
        + "\n  ".join(offenders)
    )


def test_kb060_docstrings_that_promise_scrubbing_must_call_the_scrubber():
    """**声称脱敏的函数，必须真的调脱敏。**

    这一路反复出现的形状：写下来的承诺没有人核对（V96 的「在管理后台做」、
    V99 的「必须换人」、V101 的 `can_invoice`、V103 的 SLA、V106 的
    eslint 豁免）。这一批是第六次，而且代价是个人信息。

    所以把它变成闸门：经验相关模块里，**函数里任何地方**（docstring 或注释）
    写了「脱敏」，这个函数体内就必须出现 `scrub_text`。

    扫注释而不是只扫 docstring：知识库那一处的承诺原本就写在**注释**里
    （`# 脱敏（KB-002）：只保留类目/城市/价格/工期，不含个人信息`），
    只扫 docstring 的话，这一批要修的那个原始案例根本扫不到——
    闸门第一版就是这样，自检当场说「只找到 1 个」。
    """
    import ast
    from pathlib import Path

    repo = Path(__file__).resolve().parents[2]
    targets = [
        repo / "server" / "app" / "modules" / "knowledge" / "service.py",
        repo / "server" / "app" / "modules" / "verify" / "service.py",
    ]
    offenders, checked = [], 0
    for path in targets:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            src = "\n".join(
                path.read_text(encoding="utf-8").splitlines()[
                    node.lineno - 1:(node.end_lineno or node.lineno)])
            if "脱敏" not in src:
                continue
            checked += 1
            if "scrub_text" not in src:
                offenders.append(f"{path.name}::{node.name}")
    assert checked >= 2, f"只找到 {checked} 个声称脱敏的函数，扫描可能坏了"
    assert not offenders, (
        "这些函数的 docstring 说了「脱敏」，而函数体里没有任何脱敏调用——"
        "又一句没人核对的承诺：\n  " + "\n  ".join(offenders)
    )
