"""CI-001 本地回归全绿、GitHub CI 却四项红（从 9 月 7 日起一直红）的那几处，钉住不再回来。

本地开发容器与 CI 机器不一样：根目录 node_modules 全装着、浏览器预装在 /opt、Postgres 免密。
CI 上：App 的 job 只装 app 自己的依赖、后端 job 不装前端依赖、浏览器由 Playwright 自己装、库有密码。
"""
import json
import os
import re

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")


def test_restore_drill_hands_the_password_to_pg_tools_via_env():
    from scripts.restore_drill import _pg_env

    assert _pg_env("postgresql+psycopg://postgres:c%40i@localhost:5432/acc")["PGPASSWORD"] == "c@i"
    os.environ.pop("PGPASSWORD", None)
    assert "PGPASSWORD" not in _pg_env("postgresql+psycopg://postgres@localhost/acc")
    src = open(os.path.join(ROOT, "server", "scripts", "restore_drill.py"), encoding="utf-8").read()
    invocations = len(re.findall(r'\["(?:pg_dump|psql)"', src))
    assert invocations >= 4 and src.count("env=env") == invocations, "每一次 pg_dump / psql 都要带上 env（密码）"


def test_e2e_does_not_require_the_dev_container_browser():
    src = open(os.path.join(ROOT, "server", "scripts", "e2e_web.py"), encoding="utf-8").read()
    assert 'executable_path="/opt/' not in src, "写死开发容器的浏览器路径，CI 上没有这个文件"
    assert "os.path.exists(local_chrome)" in src


def test_app_jest_falls_back_to_app_node_modules_for_shared_sdk_sources():
    """CI-001 要的兜底仍在；CI-004 起换了写法。

    CI-001 把 `<rootDir>/node_modules` 写进 `moduleDirectories`：绝对路径会在**每一层**目录的查找里都插一次，
    jest 自己的内部模块（jest-circus 的 pretty-format 29）于是先找到 app 顶层那份 24.9——任何一条 App 断言失败时，
    jest 格式化错误信息就崩（`_prettyFormat.format is not a function`），看不到哪条失败，负载高时还会挂住。
    改成 `modulePaths`（等同 NODE_PATH：正常的逐层查找都找不到才兜底）。原断言「在 moduleDirectories 里」随之退役，
    换成下面更严的三条（193 号 spec 第 6 节写明）。"""
    cfg = json.load(open(os.path.join(ROOT, "app", "package.json"), encoding="utf-8"))["jest"]
    assert "<rootDir>/node_modules" in cfg.get("modulePaths", []), \
        "packages/core 的源码在 CI 上向上找不到根 node_modules（App job 只装 app 的依赖）"
    assert not [d for d in cfg.get("moduleDirectories", []) if "/" in d or d.startswith("<")], \
        "moduleDirectories 里不许放绝对路径：会抢在 jest 自己的依赖前面"


def test_local_regression_runs_app_tests_in_the_ci_dependency_layout():
    """CI-002：本地回归里有一步按 CI 的布局（只有 app 的依赖、没有根 node_modules）跑引用共享 SDK 的单测。"""
    src = open(os.path.join(ROOT, "tools", "regress.sh"), encoding="utf-8").read()
    assert "--exclude='./app/node_modules'" in src and 'cd "$C/app"' in src
    assert "步骤失败（退出码 $rc）：CI 依赖布局下的 App 单测" in src


def test_esbuild_parse_tests_skip_without_frontend_deps_instead_of_failing():
    for name in ("test_app_parallax.py", "test_app_video_feed.py"):
        src = open(os.path.join(ROOT, "server", "tests", name), encoding="utf-8").read()
        assert 'os.path.join(ROOT, "node_modules", ".bin", "esbuild")' in src, name


def test_local_regression_checks_frontend_exit_codes_not_just_the_tests_line():
    """CI-002：vitest 测试全过但有「未处理的异步错误」时退出码是 1、CI 红；本地回归只 grep「Tests」那行，看到的是绿。"""
    src = open(os.path.join(ROOT, "tools", "regress.sh"), encoding="utf-8").read()
    for step in ("SDK 单元测试", "Web 单元测试", "App 单元测试", "Web 类型检查", "Web 构建"):
        assert f"步骤失败（退出码 $rc）：{step}" in src, step
    assert src.count("rc=${PIPESTATUS[0]}") >= 4, "管道里要取测试命令自己的退出码，不是 grep 的"
    assert "Errors |FAIL" in src, "vitest 的「Errors  N errors」那行要留在输出里"
    fail_regex = re.search(r'grep -qE "([^"]+)" "\$W/be.txt"', src).group(1)
    assert "步骤失败" in fail_regex.split("|"), "写了「步骤失败」却不算失败，等于没写"
