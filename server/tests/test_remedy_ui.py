"""CLI-073 服务端说「请先 X」，X 就必须在客户端有入口（66 号 spec）。

探针：共享 SDK 245 个方法，Web 用到 135 个，**App 只用到 33 个**。
名单里第一个刺眼的词是 `withdraw`——App 的钱包页有充值、没有提现。
那 Web 呢？Web 有提现按钮，按下去：

    WITHDRAW: 400 {"code":"no_payout_account","message":"请先绑定收款账户"}

而 `bindPayoutAccount` 在 `web/src` 和 `app/` 里**一次都没有被调用过**。
合起来：**钱能进，不能出。**

V88 的结论是「服务端的必填如果没变成类型上的必填，就只是口头约定」。
这条是它的孪生：**服务端的「请先 X」，如果 X 在客户端没有入口，
那这句话不是提示，是死路。**

CLI-064 立过半条规矩（把服务端的拦截理由原样显示出来）。
原样显示只是第一半——**第二半是那个理由得有地方去解决。**
"""
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
CLIENT_SRC = {
    # 端 -> 该端的源码文件（排除测试：**测试里调过一次不等于用户点得到**）
    "web": [p for p in (REPO / "web" / "src").rglob("*.ts*") if ".test." not in p.name],
    "app": sorted((REPO / "app").glob("*.tsx")),
}


# 服务端错误码 -> (能解决它的 SDK 方法, 必须有入口的端, 为什么用户必须能自己解决)
#
# 判定标准：**这是一个用户自己就能解决的前置条件，而且不解决就卡死。**
# 管理员专用的、或只能等平台处理的（比如封禁申诉复核）不进表——
# 用户再怎么点也解决不了的东西，给他一个按钮只是骗他。
REMEDY_UI: dict[str, tuple[str, tuple[str, ...], str]] = {
    "no_payout_account": (
        "bindPayoutAccount", ("web", "app"),
        "不绑就永远提不出钱。服务端只会重复说「请先绑定收款账户」，"
        "而此前全仓没有任何一个界面能满足它——钱能进，不能出",
    ),
    "verification_required": (
        "verifyIdentity", ("web", "app"),
        "实名是接单、提现、领券的共同前置，卡在这里用户几乎什么都做不了",
    ),
    "agreement_update_required": (
        "acceptAgreements", ("web", "app"),
        "协议更新后不重新同意，发布/接单/资金全部被 409 挡住。"
        "App 此前只能「看」协议状态不能同意，一次协议更新就把 App 用户卡成只读",
    ),
    "captcha_required": (
        "captchaConfig", ("web",),
        "连续输错密码后要过人机验证才能再登录，过不去就是被锁在账号外面。"
        "**App 侧未接**：需要 WebView 承载第三方验证码控件，"
        "本批没有真机可验证，宁可如实记成缺口（APP-071）也不上一段没验过的原生依赖",
    ),
}


def _sources(client: str) -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in CLIENT_SRC[client])


def _strip_comments(src: str) -> str:
    """注释不是用户看得见的文案。

    第一版把注释也扫了，于是**解释「不许说风控」的那句注释自己先红了**——
    一个假报警多的闸门会被人关掉（V89 立过这条），所以先把注释去掉。
    """
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"(?<!:)//[^\n]*", "", src)


def _user_facing_strings(client: str) -> str:
    """端上会显示给用户的字面量：引号里的内容 + JSX 文本节点。"""
    src = _strip_comments(_sources(client))
    quoted = re.findall(r"'([^'\n]*)'|\"([^\"\n]*)\"|`([^`]*)`", src)
    return "\n".join(x for group in quoted for x in group if x)


def _calls(client: str, method: str) -> bool:
    """`.method(` 就算调用过。刻意宽松——这道闸门要答的是
    「这个端上到底有没有这条路」，不是「调用姿势对不对」。"""
    return re.search(r"\." + re.escape(method) + r"\s*\(", _sources(client)) is not None


# --------------------------------------------------- 扫描器自检（先于断言别人）
def test_cli073_scanner_can_actually_see_the_sources():
    """扫不到等于全绿，是最糟的一种绿（V82 的教训）。

    所以先证明扫描器真的读到了东西，再用它去判别人。
    """
    for client, files in CLIENT_SRC.items():
        assert files, f"{client} 一个源码文件都没扫到——路径写错了，闸门是假绿"
        assert len(_sources(client)) > 2000, f"{client} 源码短得不像真的"
    # 已知成员：这两个改造前就在，扫不到说明正则坏了
    assert _calls("web", "topup")
    assert _calls("app", "topup")
    # 反向：编一个不存在的方法名，必须扫不到
    assert not _calls("app", "definitelyNotAnSdkMethod")


def test_cli073_table_says_why():
    """值是**理由**，不是 True。与 MUST_REACH 同一条：
    判定标准得写下来，否则半年后没人知道该往表里加什么。"""
    assert len(REMEDY_UI) >= 4
    for code, (method, clients, why) in REMEDY_UI.items():
        assert method and method[0].islower(), f"{code} 的补救方法名不像 SDK 方法"
        assert clients, f"{code} 一个端都不要求，那它进表没有意义"
        assert len(why) >= 20, f"{code} 的理由太敷衍：{why}"


@pytest.mark.parametrize("code", sorted(REMEDY_UI))
def test_cli073_every_precondition_has_a_way_out(code):
    """表里每一条：解决它的入口，在声明的端上**真的存在**。"""
    method, clients, why = REMEDY_UI[code]
    for client in clients:
        assert _calls(client, method), (
            f"服务端会用 {code} 拦住用户，而 {client} 上没有 {method}() 的入口。\n"
            f"为什么这条必须能自己解决：{why}"
        )


def test_cli073_declared_codes_are_really_raised_by_the_server():
    """表里的错误码必须是服务端真的会抛的。

    否则这张表会慢慢变成一堆过时的猜测——**和它要防的那种漂移一模一样**。
    """
    server_src = "\n".join(
        p.read_text(encoding="utf-8") for p in (REPO / "server" / "app").rglob("*.py")
    )
    for code in REMEDY_UI:
        assert f'"{code}"' in server_src, f"{code} 服务端已经不抛了，表该清理"


def test_cli073_declared_methods_exist_in_the_shared_sdk():
    """补救方法必须是 SDK 上真有的方法——写错一个名字，
    上面那条断言会永远红，而人只会以为是界面没做。"""
    sdk = (REPO / "packages" / "core" / "src" / "client.ts").read_text(encoding="utf-8")
    for code, (method, _clients, _why) in REMEDY_UI.items():
        assert re.search(r"^  " + re.escape(method) + r"\s*\(", sdk, re.M), \
            f"{code} 声明的补救方法 {method}() 在 SDK 上不存在"


# --------------------------------------------------- APP-065 钱要能出去
def test_app065_app_wallet_can_take_money_out():
    """App 的钱包页此前**只有充值**。

    一个能收钱、不能退钱的 App 不只是体验问题，应用商店会直接打回。
    """
    assert _calls("app", "withdraw"), "App 钱包没有提现入口——钱能进不能出"
    assert _calls("app", "ledger"), "App 钱包只有三个数字，没有任何一笔流水"
    # AML-030/031 tipping-off：中性话术原样显示，**不许自己编一句「触发了风控」**
    # ——那等于告诉他哪条规则命中了，既违反保密义务，也教会他下次怎么规避。
    # 只看用户看得见的文案：注释里解释这条规矩本身不算违规。
    for client in ("web", "app"):
        shown = _user_facing_strings(client)
        for word in ("风控", "反洗钱", "可疑"):
            assert word not in shown, f"{client} 的界面文案里出现了「{word}」——中性话术必须原样显示"
    # LEDG-004 科目中文名走共享 SDK，不在端里另写一份
    assert "ledgerKindLabel" in _sources("app")


# --------------------------------------------------- PAY-030 钱真的能出去
def test_pay030_withdraw_is_blocked_by_exactly_the_declared_code(client):
    """表里写的 `no_payout_account` 必须就是服务端真的回的那个码。

    码对不上，上面那条「入口存在吗」的闸门就在守一个不存在的门。
    """
    from tests.conftest import auth, register, topup, verify_user

    u = register(client, "13900091001", "提现的人")
    verify_user(client, u, name="提现")
    topup(client, u, 50000)
    r = client.post("/api/v1/wallet/withdraw", json={"amount_cents": 10000}, headers=auth(u))
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "no_payout_account"


def test_pay030_bind_then_withdraw_completes_the_round_trip(client):
    """充值 → 绑定 → 提现，钱真的出得去；并且**回显的是脱敏卡号**。"""
    from tests.conftest import auth, register, topup, verify_user

    u = register(client, "13900091002", "提现的人")
    verify_user(client, u, name="提现")
    topup(client, u, 50000)
    b = client.put("/api/v1/wallet/payout-account",
                   json={"kind": "bank", "account_no": "6222020000000000", "holder_name": "提现"},
                   headers=auth(u))
    assert b.status_code == 200, b.text
    assert "*" in b.json()["account_no"], "回显了完整卡号——服务端本来就不该给"
    assert "6222020000000000" not in b.text

    w = client.post("/api/v1/wallet/withdraw", json={"amount_cents": 10000}, headers=auth(u))
    assert w.status_code == 200, w.text
    assert w.json()["available_cents"] == 40000
    # 账单流水里看得到这一笔——App 钱包此前只有三个数字
    kinds = [e["kind"] for e in client.get("/api/v1/wallet/ledger", headers=auth(u)).json()]
    assert any(k.startswith("withdraw") for k in kinds), f"提现没有落流水：{kinds}"


def test_app066_app_can_reach_the_verification_it_was_promised():
    """V90 给 AI 交付的待验收通知写了「可在任务详情页申请人工核验」，
    而 requestVerification 当时只在 web 上有——**上一批自己挖的坑**：
    必达通知里指了一条路，那条路在一半的端上不存在。"""
    assert _calls("app", "requestVerification")
