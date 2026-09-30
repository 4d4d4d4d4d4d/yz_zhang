"""SYNC / APPB 共享约定的防漂闸门（47 号 spec）。

这一批的起点是三次实测：

1. `cd app && npm install` → E404，README 里写的运行方式从来没成功过；
2. 一旦真的 typecheck，立刻查出 `Contract.deposit_cents` 不在共享类型里；
3. 顺着 2 往下，执行方被冻结的保证金**在两个端上都没有一处说得清楚**，
   账单流水里那一行写的是 `deposit_hold`。

三条的共同根因是：跨边界的约定被手抄了一份，然后没人对过。
所以这里的测试钉的不是「文案对不对」，是「下次漂的时候会不会红」。
"""
import ast
import json
import os
import pathlib
import re

import pytest

from app.modules.wallet import service as wallet
from tests.conftest import auth, topup
from tests.test_task_flow import match_and_fund, publish_task

ROOT = pathlib.Path(__file__).resolve().parents[2]
APP = ROOT / "app"
CORE = ROOT / "packages" / "core" / "src"


# ---------------------------------------------------------------- SYNC-001/002
def _sdk_ledger_labels() -> dict[str, str]:
    """解析 packages/core/src/ledger.ts 的 LEDGER_KIND_LABEL 键。

    正则解析 TS——DSPC-041 说过不要造通用 TS 解析器。这条不违背它：
    范围是一个已知名字的对象字面量、每行一个 `key: '值'`，
    属于「枚举 + 逐处精确正则」那一类。下面有自检兜底。
    """
    src = (CORE / "ledger.ts").read_text(encoding="utf-8")
    body = re.search(
        r"export const LEDGER_KIND_LABEL:\s*Record<string,\s*string>\s*=\s*\{(.*?)\n\};",
        src, re.S,
    )
    assert body, "没找到 LEDGER_KIND_LABEL 定义——正则失配时必须失败，不能返回空集"
    out = {}
    for line in body.group(1).splitlines():
        line = line.split("//")[0]
        m = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*:\s*'([^']*)'\s*,", line)
        if m:
            out[m.group(1)] = m.group(2)
    return out


def test_sync003_label_parser_fails_loudly_rather_than_returning_empty():
    """SYNC-003 扫描器自己不许静默失败。

    写这批时我先把 `_log(db, user_id, kind, …)` 的 kind 按 args[1] 取，
    扫出零个科目——而零个科目会让比对**全绿通过**。
    一个会静默返回空集的检查器比没有检查器更坏：它给出「已检查」的假象。
    """
    labels = _sdk_ledger_labels()
    assert len(labels) >= 16, f"只解析出 {len(labels)} 条标签，正则多半失配了"
    for known in ("deposit_hold", "escrow_hold", "tax_withheld"):
        assert known in labels


def test_sync002_server_kinds_and_sdk_labels_match_exactly():
    """服务端能产生的科目 ↔ SDK 中文名，**双向相等**。

    - SDK 缺 → 用户在账单里看英文标识符（这批修的就是这个洞：20 缺 12）；
    - SDK 多 → 服务端删过科目而文案没跟着删，是另一种漂。
    """
    labels = set(_sdk_ledger_labels())
    kinds = set(wallet.LEDGER_KINDS)
    assert not (kinds - labels), f"这些科目没有中文名，用户会看到英文：{sorted(kinds - labels)}"
    assert not (labels - kinds), f"这些中文名对应的科目服务端已不再产生：{sorted(labels - kinds)}"


def _logged_literal_kinds() -> set[str]:
    """AST 扫出 `_log()` 调用里的字面量科目。

    注意签名是 `_log(db, user_id, kind, amount, …)`——kind 是 **args[2]**。
    `transfer()` 里的 f-string 科目扫不准（前半截是调用方传的），
    那部分交给 LEDGER_KINDS 显式声明，这里只查字面量。
    """
    found = set()
    for p in (ROOT / "server" / "app").rglob("*.py"):
        for node in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
            if name == "_log" and len(node.args) >= 3:
                a = node.args[2]
                if isinstance(a, ast.Constant) and isinstance(a.value, str):
                    found.add(a.value)
    return found


def test_sync003_every_logged_kind_is_declared():
    """第二道：代码里真的写出来的科目，必须在 LEDGER_KINDS 里。

    全集声明解决「有没有中文名」，这条解决「声明会不会忘了更新」。
    """
    found = _logged_literal_kinds()
    # 扫描器自检：签名一改、扫描一瞎，先炸的是扫描器自己
    assert len(found) >= 14, f"只扫到 {len(found)} 个字面量科目，_log() 的参数位置多半变了"
    for known in ("deposit_hold", "escrow_hold", "tax_withheld"):
        assert known in found, f"{known} 没扫到，扫描器失效了"
    assert not (found - set(wallet.LEDGER_KINDS)), \
        f"这些科目写进了代码但没声明：{sorted(found - set(wallet.LEDGER_KINDS))}"


def test_sync002_log_rejects_undeclared_kind_at_write_time():
    """写入点的硬闸门：未声明的科目直接抛，不给它写进账本的机会。

    在写入点炸掉，比写进去之后靠肉眼在账单里发现一行英文便宜得多。

    传 db=None 是有意的：检查必须发生在**碰数据库之前**，
    所以一个没有 session 也能抛出来的 ValueError 恰好证明了这一点。
    """
    with pytest.raises(ValueError, match="未声明的账本科目"):
        wallet._log(None, 1, "totally_made_up_kind", 100)


def test_sync002_transfer_rejects_undeclared_prefix():
    """同上：前缀在拼出 `{kind}_out` 之前就要验，否则报错指向的是拼好的
    "bogus_out" 而不是调用方传的 "bogus"，排查时多绕一圈。"""
    with pytest.raises(ValueError, match="未声明的转账科目前缀"):
        wallet.transfer(None, 1, 2, 100, kind="bogus")


# ------------------------------------------------------------------- SYNC-004
def _sdk_contract_fields() -> set[str]:
    src = (CORE / "types.ts").read_text(encoding="utf-8")
    body = re.search(r"export interface Contract \{(.*?)\n\}", src, re.S)
    assert body, "没找到 interface Contract——正则失配时必须失败"
    fields = set()
    for line in body.group(1).splitlines():
        line = line.split("//")[0]
        m = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\??\s*:", line)
        if m:
            fields.add(m.group(1))
    assert len(fields) >= 10, f"只解析出 {len(fields)} 个字段，正则多半失配了"
    return fields


def test_sync004_contract_response_keys_are_all_declared_in_sdk(client, requester, worker):
    """服务端真实返回的每个键，SDK 的 `Contract` 类型里都要有声明。

    不靠眼睛比：真的下一单、真的取一次响应、真的对键集合。
    这条比文案闸门值钱——它查的是**前后端之间那份没人签字的约定**。

    反方向（类型里有、响应里没有）只做提示不失败：`milestones?` 这类可选
    字段在没有里程碑的合约上本来就不出现，强制双向会逼出假阳性。
    """
    topup(client, requester, 100000)
    topup(client, worker, 50000)
    task = publish_task(client, requester, deposit_cents=5000)
    cid = match_and_fund(client, requester, worker, task)
    body = client.get(f"/api/v1/contracts/{cid}", headers=auth(requester)).json()

    declared = _sdk_contract_fields()
    missing = set(body) - declared
    assert not missing, (
        f"服务端返回了这些键，但共享类型里没有声明：{sorted(missing)}。"
        f"没有客户端会去读它们——表现为「这个功能好像没做」"
    )
    # deposit 这两个正是这批的起因，钉死免得又被删掉
    assert {"deposit_cents", "deposit_status"} <= declared


# ------------------------------------------------------------------- SYNC-005
def test_sync005_no_ledger_row_reaches_the_user_without_a_chinese_label(
    client, requester, worker
):
    """复现这批的起因：执行方接单后，账单流水里出现 `deposit_hold  -¥50.00`。

    修之前这条是红的——用户的 ¥50 从可用余额消失，唯一的解释是一行英文。
    """
    topup(client, requester, 100000)
    topup(client, worker, 50000)
    task = publish_task(client, requester, deposit_cents=5000)
    match_and_fund(client, requester, worker, task)

    labels = _sdk_ledger_labels()
    for who, name in ((requester, "发布方"), (worker, "执行方")):
        rows = client.get("/api/v1/wallet/ledger", headers=auth(who)).json()
        unlabeled = [r["kind"] for r in rows if r["kind"] not in labels]
        assert not unlabeled, f"{name}的账单里有无中文名的流水：{unlabeled}"

    worker_kinds = {
        r["kind"] for r in client.get("/api/v1/wallet/ledger", headers=auth(worker)).json()
    }
    assert "deposit_hold" in worker_kinds, "这条测试要有保证金流水才有意义"


# -------------------------------------------------------------------- APPB
def _app_package() -> dict:
    return json.loads((APP / "package.json").read_text(encoding="utf-8"))


def test_appb001_core_dependency_is_resolvable():
    """`"@platform/core": "*"` 会让 npm 去 registry 找一个不存在的公开包。

    实测 `cd app && npm install` 报 E404 —— README 里写的那条命令
    从落笔那天起就没成功过。改成 file: 协议后实测 1139 个包、29 秒装完。
    """
    dep = _app_package()["dependencies"]["@platform/core"]
    assert dep.startswith("file:"), (
        f"@platform/core 声明为 {dep!r}：app 不是根 workspace 成员，"
        f"非 file: 协议会让 npm 去公共 registry 找这个包并 404"
    )
    assert (APP / dep[len("file:"):]).resolve().is_dir()


def test_appb005_every_declared_expo_plugin_is_an_installed_dependency():
    """app.json 里声明的每个 config plugin，都必须是已声明的依赖。

    这条和 VID-041 同类但查不同的东西：VID-041 查 import，
    **看不见配置文件里的插件名**。而插件解析失败同样是硬失败，
    且只在 prebuild / 打包时暴露——最晚、最贵的那个时刻。

    修之前这条是红的：app.json 声明了 expo-image-picker，
    而它既不在 dependencies 里，也没有任何一行代码 import 它。
    """
    pkg = _app_package()
    deps = set(pkg["dependencies"]) | set(pkg.get("devDependencies", {}))
    plugins = json.loads((APP / "app.json").read_text(encoding="utf-8"))["expo"]["plugins"]
    names = [p if isinstance(p, str) else p[0] for p in plugins]
    assert names, "这条测试要有插件才有意义"
    missing = [n for n in names if n not in deps]
    assert not missing, (
        f"app.json 声明了这些插件但没装：{missing}。"
        f"expo prebuild / EAS build 会直接失败在插件解析上"
    )


def test_appb002_babel_config_exists_with_expo_preset():
    """没有 babel.config.js，Metro 就没有 babel-preset-expo，
    第一个 <View> 就是语法错误——`expo start` 根本起不来。"""
    # 去注释：V58 那次教训——断言钉的是代码，不是描述代码的散文
    src = "\n".join(
        line.split("//")[0] for line in (APP / "babel.config.js").read_text().splitlines()
    )
    assert "babel-preset-expo" in src


def test_appb003_metro_config_reaches_the_workspace_package():
    """@platform/core 是 app/ 之外的 TS 源码，Metro 默认看不见。"""
    src = "\n".join(
        line.split("//")[0] for line in (APP / "metro.config.js").read_text().splitlines()
    )
    assert "watchFolders" in src and "packages/core" in src
    assert "nodeModulesPaths" in src


def test_appb006_typecheck_is_configured():
    pkg = _app_package()
    assert pkg["scripts"].get("typecheck") == "tsc --noEmit"
    for dev in ("typescript", "@types/react"):
        assert dev in pkg["devDependencies"], f"typecheck 需要 {dev}"
    tsconfig = json.loads((APP / "tsconfig.json").read_text(encoding="utf-8"))
    assert tsconfig["compilerOptions"]["strict"] is True


def test_appb006_ci_runs_app_typecheck():
    """闸门要真的在 CI 里跑，否则只是仓库里的一个文件。"""
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "app-typecheck" in ci
    assert "npm run typecheck" in ci
