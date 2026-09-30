"""SCR-010 仓里的脚本有没有人跑（84 号 spec）。

这一篇的由来：`scripts/loadtest.py` **从 V77 起就跑不起来了**——那一批把
`ip_assignment` 变成发任务的必填项，而这个脚本的请求体没跟着改。它坏了
33 个批次没有人知道，因为**没有任何地方跑它**：不在 CI 里、不在回归里、
不在部署脚本里。同时 `docs/OPERATIONS.md` 一直印着它 V65 那一次的数字，
当作「当前容量基线」。

`scripts/seed_demo.py` 是同一回事，而且更难看：README 让新来的人第一件事
就跑它，而它会以 `KeyError: 'id'` 崩掉——**新人看到的第一个输出是 KeyError**。

所以这一篇钉两件事：

1. 每个脚本都要有人跑，或者在声明表里写清为什么不跑（值是方式，不是布尔）；
2. 声明「回归里跑」的，这里就**真的把它跑一遍**——写下「有人跑」而没有
   人跑，正是这一路反复出现的那个形状（第九次）。
"""
import ast
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from tests.conftest import auth

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "server" / "scripts"
CI = REPO / ".github" / "workflows" / "ci.yml"

# 脚本 -> 谁在跑它。值是**方式**，不是布尔（V90 那条）。
# 「没有人跑」不许出现在这张表里：那不是一种方式，那是这一篇要修的病。
EXERCISED: dict[str, str] = {
    "smoke.py": "CI 的 boot-smoke job（真实 HTTP 主闭环）",
    "sandbox_check.py": "CI 的 sandbox-compliance job",
    "e2e_web.py": "CI 的 web-e2e job（真 Chromium）",
    "acceptance.py": "CI 的 postgres-acceptance job + deploy/oneclick.sh",
    "restore_drill.py": "CI 的 restore-drill job + deploy/restore.sh",
    "loadtest.py": "CI 的 boot-smoke job 跑一小轮（只证明还能跑，不做容量判断）"
                   "+ 回归里核对它的请求体",
    "cron.py": "deploy 的 worker 容器 + 回归里与调度表双向核对",
    "consistency_check.py": "deploy/restore.sh 恢复后校验 + 回归引用",
    "seed_demo.py": "回归里真的跑一遍（本文件）",
    "scrub_experience.py": "回归里跑 --dry-run（本文件）；生产是开站前手动跑一次",
}


def _script_names() -> set[str]:
    return {p.name for p in SCRIPTS.glob("*.py") if not p.name.startswith("_")}


def test_scr010_scanner_finds_the_scripts():
    """扫不到等于全绿，是最糟的一种绿。"""
    names = _script_names()
    assert len(names) >= 8, f"只扫到 {len(names)} 个脚本，提取逻辑可能坏了"
    for known in ("smoke.py", "loadtest.py", "seed_demo.py"):
        assert known in names, f"{known} 明明在 scripts/ 里，扫描却说没有"


def test_scr010_every_script_is_exercised_somewhere():
    """新加一个脚本，要么有人跑，要么在表里写明是谁在跑。"""
    names = _script_names()
    missing = sorted(names - set(EXERCISED))
    assert not missing, (
        "这些脚本没有在 EXERCISED 表里交代是谁在跑：\n  " + "\n  ".join(missing)
        + "\n一个没有人跑的脚本会静默腐烂，而它印在文档里的数字会继续被人当真。"
    )
    stale = sorted(set(EXERCISED) - names)
    assert not stale, f"表里这些脚本已经不在 scripts/ 里了：{stale}"


def test_scr010_claims_about_ci_are_true():
    """声明「CI 里跑」的，ci.yml 里必须真的有它。

    这一条防的是**把「有人跑」写进表里就算完**——那正是这一批在修的病，
    只是换了个地方犯。
    """
    ci = CI.read_text(encoding="utf-8")
    for name, how in sorted(EXERCISED.items()):
        if "CI" not in how:
            continue
        module = name[:-3]
        assert f"scripts.{module}" in ci, (
            f"{name} 的表里写着「{how}」，而 ci.yml 里找不到 scripts.{module}"
        )


# ---------- 声明「回归里跑」的，这里真的跑 ----------
def _fresh_db(tmp: str) -> dict:
    """给脚本一个空库跑，不碰共享的测试库。"""
    url = f"sqlite:///{tmp}/rot.db"
    env = {**os.environ, "PLATFORM_DATABASE_URL": url, "PLATFORM_ENV": "sandbox"}
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"],
                   cwd=str(REPO / "server"), env=env, check=True,
                   capture_output=True)
    return env


def test_scr011_seed_demo_really_runs():
    """演示数据脚本必须真的能生成数据。

    它此前**一条任务都建不出来**：四次发布全部 400（漏 `ip_assignment`），
    而脚本一次都不看状态码，于是在三十行之后以 `KeyError: 'id'` 崩掉——
    那个位置离病因太远，读栈的人会去查 `/applications`，坏的却是 `/tasks`。

    修好之后又立刻暴露第二处腐烂：三个演示用户**共用一个证件号**，
    而平台后来加了一人多号检测，第二、三个人的实名静默 409，于是他们
    报不了名，闭环那一段一条数据也生成不出来。两处都是「加了新约束，
    而没有人跑的脚本不会告诉你」。

    所以这里不只断言退出码 0，还**数一遍落库的行**：退出 0 而库里是空的，
    是这个脚本此前的真实状态（前三次发布失败也照样往下走）。
    """
    import sqlite3

    with tempfile.TemporaryDirectory() as tmp:
        env = _fresh_db(tmp)
        proc = subprocess.run([sys.executable, "-m", "scripts.seed_demo"],
                              cwd=str(REPO / "server"), env=env, capture_output=True,
                              text=True, timeout=600)
        assert proc.returncode == 0, f"seed_demo 跑不起来：\n{proc.stdout[-2000:]}"

        db = sqlite3.connect(f"{tmp}/rot.db")
        counts = {t: db.execute(f"select count(*) from {t}").fetchone()[0]
                  for t in ("users", "tasks", "contracts", "reviews",
                            "knowledge_cards", "circles", "contents")}
        db.close()
    # 每一类都必须有：闭环那一段（合约/评价/经验卡）是最容易静默失败的部分
    for table, n in sorted(counts.items()):
        assert n > 0, f"seed_demo 退出 0，但 {table} 是空的：{counts}"


def test_scr011_seed_demo_run_twice_is_clean():
    """跑第二遍要正常退出并说明数据已存在。

    这一条是我自己踩出来的：给每步加上状态码检查之后，第二次跑直接
    退出 1（`already_verified` 被当成失败）——**把一个静默 bug 换成了
    正当用法上的硬失败，那不是修好**。

    修法不是给 409 开一串放行口（那会连 `id_already_bound` 一起放过，
    而那正是这一批修掉的另一个缺陷），而是认清这个脚本的目标状态是
    「演示数据存在」：已经存在就说清楚并正常退出。也不做成可反复追加——
    追加一遍就多四条任务、多一份合约，圈层名还会撞，
    **一个跑两次就得到一份说不清的数据集的演示脚本，比拒绝跑更糟**。
    """
    with tempfile.TemporaryDirectory() as tmp:
        env = _fresh_db(tmp)
        first = subprocess.run([sys.executable, "-m", "scripts.seed_demo"],
                               cwd=str(REPO / "server"), env=env, capture_output=True,
                               text=True, timeout=600)
        assert first.returncode == 0, f"首跑失败：\n{first.stdout[-1500:]}"
        second = subprocess.run([sys.executable, "-m", "scripts.seed_demo"],
                                cwd=str(REPO / "server"), env=env, capture_output=True,
                                text=True, timeout=600)
        assert second.returncode == 0, f"第二次跑失败：\n{second.stdout[-1500:]}"
        assert "已存在" in second.stdout, f"第二次跑没有说明数据已存在：{second.stdout[-300:]}"


def test_scr011_scrub_experience_dry_run_really_runs():
    """存量脱敏脚本必须能在空库上跑完并且**什么都不改**。

    空库跑通只证明它没语法错、连得上库；`--dry-run` 不写库这件事同样要钉住，
    因为这是一个**动用户数据**的脚本，误在生产上跑一次真写是不可逆的。
    """
    with tempfile.TemporaryDirectory() as tmp:
        env = _fresh_db(tmp)
        proc = subprocess.run(
            [sys.executable, "-m", "scripts.scrub_experience", "--dry-run"],
            cwd=str(REPO / "server"), env=env, capture_output=True, text=True, timeout=300)
        assert proc.returncode == 0, f"scrub_experience 跑不起来：\n{proc.stdout[-2000:]}"
        assert "没有写库" in proc.stdout, f"--dry-run 没有声明它不写库：{proc.stdout[-300:]}"


def test_scr012_loadtest_payloads_are_accepted_by_the_server(client, requester):
    """压测脚本手写的请求体，必须是服务端真的认的。

    这一条是这一批的核心闸门，而且它**不需要起服务、不需要跑负载**：
    直接把脚本里的请求体打到服务端，看是不是 201。坏掉的方式就是
    V77 那一次——服务端多了一个必填项，而脚本的请求体没跟着改。

    为什么不靠「CI 里跑一小轮」兜住这件事就够了：CI 那一轮能发现同样的问题，
    但它要起服务、要几十秒；这一条在回归里几毫秒就红，**红得越早越便宜**。
    """
    from scripts.loadtest import TASK_BODY, register_body

    body = register_body()
    assert set(body) == {"phone", "password", "nickname", "sms_code"}, \
        f"注册请求体的键变了，压测脚本要跟着改：{sorted(body)}"

    resp = client.post("/api/v1/tasks", json=dict(TASK_BODY), headers=auth(requester))
    assert resp.status_code == 201, (
        f"压测脚本的发任务请求体被服务端拒绝：{resp.status_code} {resp.text[:300]}\n"
        "服务端加了必填项就要同步改 scripts/loadtest.py 的 TASK_BODY。"
    )


def test_scr012_write_scenario_uses_the_same_body():
    """write 场景不许自己抄一份请求体。

    原来它有**独立的一份副本**，也漏了 `ip_assignment`。它比 setup 那处更
    危险：setup 会炸，而这里只让每次请求被 400 挡掉，然后把**拒绝的速率**
    报成写入吞吐量——**一个把 400 当吞吐量的压测，比没有数字更糟**，
    因为它看起来很正常。第二份实现必然抄漏（这一路第 N 次）。
    """
    src = (SCRIPTS / "loadtest.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    # 模块里只许有一处写着 "title": ... 的字面量请求体（TASK_BODY 那一处）
    literal_bodies = [n for n in ast.walk(tree) if isinstance(n, ast.Dict)
                      and any(isinstance(k, ast.Constant) and k.value == "title"
                              for k in n.keys if k is not None)]
    assert len(literal_bodies) == 1, (
        f"loadtest.py 里有 {len(literal_bodies)} 份字面量任务请求体，应当只有 TASK_BODY 一份"
    )


def test_scr013_contract_failures_fail_the_run():
    """400/422 一次都不许被当成吞吐量；429/503 不算失败。

    两种失败对「这组数字能不能用」的含义**相反**：请求体对不上（400/422）
    意味着压的是被拒绝的快路径，数字测的不是业务；限流与过载（429/503）
    恰恰是压测想看到的东西，把它算成失败等于不许压测压出结果。
    """
    src = (SCRIPTS / "loadtest.py").read_text(encoding="utf-8")
    assert "(400, 422)" in src, "没有把契约性失败单独判死"
    assert "return 1" in src, "契约性失败不会让脚本以非零退出"
    # 反向：不许把 429/503 也判死，否则压测压不出结果
    for capacity_code in ("429", "503"):
        assert f"c in ({capacity_code}" not in src, \
            f"{capacity_code} 被当成了契约性失败——那是容量信号，不是缺陷"
