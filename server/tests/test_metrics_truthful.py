"""LINT-001 指标说真话 + 后端「会红在真问题上」的静态检查（139 号 spec）。

一条实测出来的缺陷：`_pending_uploads` 用了没导入的 `func`，NameError 被它自己的 `except Exception`
吞掉，`platform_uploads_pending_review` 恒为 0。`deploy/alerts.prom.yml` 里「审核积压 > 500」那条告警
因此永远不会响——而且是静默的。DRILL-041 已经说过：配了却从不告警的监控比没有监控更危险。

三道闸门：
1. 这个指标要真的数（行为验）；
2. 指标端点里兜底的 `except` 必须留日志——能兜，但不能悄悄兜；
3. 未定义的名字、重复字典键这类**一定是错**的问题，用 ruff 在 app/ 与 scripts/ 里查（只开这几条规则）。
"""
import ast
import os
import shutil
import subprocess
import uuid

import pytest

from app.core.db import SessionLocal
from tests.conftest import JOB_HEADERS

HERE = os.path.dirname(__file__)
SERVER = os.path.abspath(os.path.join(HERE, ".."))
OBS = os.path.join(SERVER, "app", "core", "observability.py")
# 只开「一定是错」的规则：未定义名字、__all__ 里不存在的名字、赋值前使用、对字面量用 is、字典键重复、
# 语法层面的 yield/return/break 误用。风格类一条不开（理由同前端 APPB-052b）
# LINT-004（262 号 spec，V289）例外：未用导入（F401）。清到 0 之后它只会在新代码里出现、改一行就好，
# 不会逼人加 --quiet；留着它，读代码的人会以为那个名字在这里有用（V168 的 func 就是反过来的同一类错）
RULES = "F821,F822,F823,F632,F601,F7,F401,F841,F811"
# LINT-007（270 号 spec，V297）只查 app/ 与 scripts/ 的规则：重复定义（F811）在测试里会误报
# ——按名字注入的 pytest fixture 从别的文件导进来、再作为参数出现，就是 F811 的样子
# LINT-008（290 号 spec，V317）跨文件共用的 fixture 挪进 conftest 后，F811 也进了上面四个目录的 RULES；
# 这一组仍单独跑一遍 app/ 与 scripts/（只增不减）
APP_ONLY_RULES = "F811"


def _metric(text: str, name: str) -> int:
    line = next(x for x in text.splitlines() if x.startswith(name + " "))
    return int(line.split()[1])


def test_pending_uploads_metric_counts_the_review_queue(client):
    from app.modules.files.models import UploadedFile

    before = _metric(client.get("/metrics", headers=JOB_HEADERS).text, "platform_uploads_pending_review")
    with SessionLocal() as db:
        for status in ("review", "review", "pass"):
            db.add(UploadedFile(name=uuid.uuid4().hex, owner_id=1, sha256="0" * 64, content_type="image/png",
                                moderation_status=status))
        db.commit()
    after = _metric(client.get("/metrics", headers=JOB_HEADERS).text, "platform_uploads_pending_review")
    assert after == before + 2, "审核积压指标没有跟着待审数量变——告警会永远不响"


def test_a_swallowed_metric_error_is_logged(client, monkeypatch, caplog):
    from app.modules.risk import service as risk

    def boom(_db):
        raise RuntimeError("聚合炸了")

    monkeypatch.setattr(risk, "reconcile", boom)
    with caplog.at_level("ERROR", logger="app.error"):
        assert client.get("/metrics", headers=JOB_HEADERS).status_code == 200
    assert any("reconcile_ok" in r.getMessage() for r in caplog.records), "兜底了却没留痕"


def test_every_fallback_in_the_metrics_module_leaves_a_trace():
    """observability.py 的模块级函数（指标的计算都在这里）里，每个 `except Exception` 要么记日志、要么重新抛出——
    不许悄悄返回一个安全值。日志格式化器自己的兜底不在此列：它没法再记日志（会递归），用的是一条占位输出。"""
    tree = ast.parse(open(OBS, encoding="utf-8").read())
    funcs = [f for f in tree.body if isinstance(f, ast.FunctionDef)]
    assert any(f.name == "_pending_uploads" for f in funcs)
    silent = []
    for node in (n for f in funcs for n in ast.walk(f)):
        if not isinstance(node, ast.ExceptHandler):
            continue
        if not (isinstance(node.type, ast.Name) and node.type.id == "Exception"):
            continue
        calls = [c for c in ast.walk(node) if isinstance(c, ast.Call)]
        logs = any(isinstance(c.func, ast.Attribute) and c.func.attr in ("exception", "error", "warning")
                   for c in calls)
        reraises = any(isinstance(n, ast.Raise) for n in ast.walk(node))
        if not (logs or reraises):
            silent.append(node.lineno)
    assert not silent, f"observability.py 第 {silent} 行的 except Exception 悄悄吞了错误"


def ruff_missing_action(env) -> str:
    """LINT-005（280 号 spec，V308）没装 ruff 时怎么办：CI（GitHub Actions 自带 CI=true）与全量回归
    （tools/regress.sh 设 PLATFORM_REQUIRE_RUFF=1）里必须**失败**——静默跳过等于这条闸门不存在；
    只有开发者本机随手跑时才跳过。"""
    return "fail" if env.get("CI") or env.get("PLATFORM_REQUIRE_RUFF") else "skip"


def test_ruff_missing_fails_where_it_must():
    assert ruff_missing_action({"CI": "true"}) == "fail"
    assert ruff_missing_action({"PLATFORM_REQUIRE_RUFF": "1"}) == "fail"
    assert ruff_missing_action({}) == "skip"


def test_no_names_that_are_certainly_wrong():
    if shutil.which("ruff") is None:
        msg = "本机没有 ruff：pip install ruff==0.15.8（与 ci.yml 一致）"
        if ruff_missing_action(os.environ) == "fail":
            pytest.fail(msg + "；CI 与全量回归里不能跳过这条静态检查")
        pytest.skip(msg)
    # LINT-006（264 号 spec，V291）范围扩到 tests/ 与 migrations/：测试里写错名字一样会让断言悄悄不跑
    r = subprocess.run(["ruff", "check", "--no-cache", "--select", RULES, "--output-format", "concise",
                        "app", "scripts", "tests", "migrations"],
                       cwd=SERVER, capture_output=True, text=True)
    assert r.returncode == 0, "这些一定是错：\n" + r.stdout + r.stderr
    r = subprocess.run(["ruff", "check", "--no-cache", "--select", APP_ONLY_RULES, "--output-format", "concise", "app", "scripts"],
                       cwd=SERVER, capture_output=True, text=True)
    assert r.returncode == 0, "这些一定是错：\n" + r.stdout + r.stderr
