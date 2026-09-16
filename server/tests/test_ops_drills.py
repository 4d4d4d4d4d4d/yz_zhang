"""DRILL-010~042 那些「从来没验证过」的东西（40 号 spec）。

我在上一次状态汇报里说过，这一类是我最没底的部分：压测、告警、备份恢复演练、
依赖扫描——**一次都没做过**。这一批把它们做掉，并且把结论钉成测试。

写 `deploy/alerts.prom.yml` 的过程本身就抓到一个：我写的前三条告警
（资金不平、job 静默、审核积压）引用的指标 `/metrics` 根本不暴露。
**引用不存在指标的告警永远不会触发，而且是静默的。**
一个「配了却从不告警」的监控比没有监控更危险——你以为自己被盖住了。
所以这里的核心断言是：告警规则里出现的每一个指标名，都必须真的被暴露。
"""
import os
import re
import subprocess
import sys

import yaml

from .conftest import JOB_HEADERS

REPO = os.path.join(os.path.dirname(__file__), "..", "..")
ALERTS = os.path.join(REPO, "deploy", "alerts.prom.yml")
CI = os.path.join(REPO, ".github", "workflows", "ci.yml")


def metric_names(text: str) -> set[str]:
    """从 /metrics 输出里取出所有指标名。"""
    return {
        line.split()[0] for line in text.splitlines()
        if line and not line.startswith("#") and line.split()[0].startswith("platform_")
    }


# ---------- DRILL-041 告警引用的指标必须真的存在 ----------
def test_drill041_every_alerted_metric_is_actually_exposed(client):
    """这条就是本批自己踩到的坑。

    告警规则不会因为指标名写错而报错——它只是永远沉默。
    没有这条断言，`platform_reconcile_ok` 这个最重要的告警会一直是个摆设。
    """
    exposed = metric_names(client.get("/metrics", headers=JOB_HEADERS).text)
    assert exposed, "指标端点没有输出任何 platform_* 指标"

    rules = yaml.safe_load(open(ALERTS))
    referenced = set()
    for group in rules["groups"]:
        for rule in group["rules"]:
            referenced |= set(re.findall(r"\bplatform_\w+", rule["expr"]))

    missing = sorted(referenced - exposed)
    assert not missing, (
        f"这些告警规则引用的指标 /metrics 并不暴露：{missing}。"
        "引用不存在指标的告警永远不会触发，而且是静默的——"
        "一个「配了却从不告警」的监控比没有监控更危险。"
    )


def test_alert_rules_are_structurally_valid():
    """promtool 在本环境跑不了（没有 Prometheus），所以至少把结构钉住。

    这不等于 promtool 校验过——落地前仍须跑 `promtool check rules`，
    规则文件头部写了这句。
    """
    rules = yaml.safe_load(open(ALERTS))
    assert rules["groups"]
    for group in rules["groups"]:
        assert group.get("name") and group.get("rules")
        for rule in group["rules"]:
            assert rule.get("alert"), f"{group['name']} 里有规则没有 alert 名"
            assert rule.get("expr"), f"{rule.get('alert')} 没有表达式"
            assert rule.get("labels", {}).get("severity") in ("critical", "warning"), \
                f"{rule['alert']} 没有 severity——值班的人无法分流"
            assert rule.get("annotations", {}).get("summary"), \
                f"{rule['alert']} 没有 summary——半夜被叫醒的人看不懂"


def test_drill040_the_reconciliation_metric_reflects_reality(client):
    """资金对账这条最重要的告警，指标必须真的算了对账而不是常数 1。"""
    text = client.get("/metrics", headers=JOB_HEADERS).text
    assert "platform_reconcile_ok 1" in text          # 干净库应当是平的

    from app.core.db import SessionLocal
    from app.modules.wallet.models import WalletAccount

    db = SessionLocal()
    acct = WalletAccount(user_id=99999, available_cents=12345)   # 凭空多出一笔钱
    db.add(acct)
    db.commit()
    db.close()

    text = client.get("/metrics", headers=JOB_HEADERS).text
    assert "platform_reconcile_ok 0" in text, "把钱凭空加进去，对账指标却没变——它不是在真算"


def test_metrics_endpoint_survives_a_broken_aggregate(client, monkeypatch):
    """一个聚合出错不能让整个指标端点 500——那会让**所有**告警一起瞎掉。"""
    from app.modules.risk import service as risk

    def boom(_db):
        raise RuntimeError("聚合炸了")

    monkeypatch.setattr(risk, "reconcile", boom)
    r = client.get("/metrics", headers=JOB_HEADERS)
    assert r.status_code == 200
    assert "platform_reconcile_ok 0" in r.text        # 算不出来按最坏情况报


# ---------- DRILL-020 备份恢复演练 ----------
def test_drill020_restore_drill_actually_runs_and_passes(tmp_path):
    """真的跑一遍：造闭环 → 备份 → **删库** → 恢复 → 校验。

    一份没有恢复过的备份，不是备份，是一个关于备份的假设。
    """
    env = dict(os.environ, DRILL_DB=str(tmp_path / "drill.db"))
    env.pop("PLATFORM_DATABASE_URL", None)
    proc = subprocess.run(
        [sys.executable, "-m", "scripts.restore_drill"],
        cwd=os.path.join(os.path.dirname(__file__), ".."),
        env=env, capture_output=True, text=True, timeout=300,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "演练通过" in proc.stdout


def test_drill010_restore_script_uses_the_shared_consistency_check():
    """生产恢复跑的那段校验，必须就是演练跑的那段。

    此前它是 `restore.sh` 里的一个 heredoc——写得很对，但只存在于一个需要
    完整生产栈 + 人工敲 yes 才跑得到的地方，所以一次都没被执行过。
    两份实现迟早会漂移，而漂移的那一天你正在恢复生产库。
    """
    sh = open(os.path.join(REPO, "deploy", "restore.sh")).read()
    assert "scripts.consistency_check" in sh
    assert "risk.reconcile" not in sh, "校验逻辑又被内联回 shell 里了"


# ---------- DRILL-030 压测脚本 ----------
def test_drill030_loadtest_reports_the_numbers_that_matter():
    """压测脚本必须给出分位数与错误率，而不只是一个平均值。

    平均值会把「一半请求 60ms、另一半 2 秒」显示成一个好看的数字。
    """
    src = open(os.path.join(os.path.dirname(__file__), "..", "scripts", "loadtest.py")).read()
    for key in ("p50_ms", "p95_ms", "p99_ms", "error_rate", "throughput_rps"):
        assert key in src, f"压测输出缺少 {key}"
    # 不设阈值断言是有意的：容量取决于机器，写死一个数字只会在别人的机器上误报
    assert "不设阈值断言" in src


# ---------- DRILL-050 CI 真的跑这些 ----------
def test_drill050_ci_runs_the_audits_and_the_drill():
    """写了脚本不进 CI，等于又造了一个没人跑的东西。"""
    ci = yaml.safe_load(open(CI))
    jobs = ci["jobs"]
    assert "dependency-audit" in jobs and "restore-drill" in jobs

    audit = yaml.safe_dump(jobs["dependency-audit"], allow_unicode=True)
    assert "pip-audit" in audit
    # 发给用户的依赖是硬闸门；构建工具链只报告不阻断
    assert "--omit=dev" in audit
    assert "npm audit || true" in audit

    drill = yaml.safe_dump(jobs["restore-drill"], allow_unicode=True)
    assert "scripts.restore_drill" in drill
