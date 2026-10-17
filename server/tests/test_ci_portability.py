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


def test_local_regression_typechecks_the_app_like_ci_does():
    """CI-005：GitHub CI 的 App job 会做类型检查；本地回归以前只查 Web，App 测试文件里的类型错误本地放得过去。"""
    src = open(os.path.join(ROOT, "tools", "regress.sh"), encoding="utf-8").read()
    assert "( cd app && npx tsc --noEmit" in src
    assert "步骤失败（退出码 $rc）：App 类型检查" in src


# CI-006（200 号 spec）：GitHub CI 的每个 job，要么本地回归里有对应的步骤，要么写明为什么只在 CI 上跑。
# 新加的 CI job 不归类，这条测试就红——「本地绿、CI 红」的来源就是两边检查项对不上（CI-001/003/004/005）。
LOCAL_STEPS: dict[str, list[str]] = {
    "backend": ["python -m pytest"],
    "frontend": ["npm test -w packages/core", "npm test -w web", "npx eslint", "npx tsc -p web",
                 'check_frontend_counts --dir "$J" core web', "npm run build:web"],
    "app-typecheck": ["( cd app && npx tsc --noEmit", "npx jest --json", 'check_frontend_counts --dir "$J" app'],
    "web-e2e": ["scripts.e2e_web"],
    "sandbox-compliance": ["scripts.sandbox_check"],
    "migration-drift": ["alembic check"],
}
CI_ONLY: dict[str, str] = {
    "smart-contracts": "合约是单独的 Hardhat 工程，要下载 EVM 编译器；本地回归不装这套依赖，合约改动在 CI 上看",
    "boot-smoke": "要起独立的服务进程跑完一笔真实交易与压测脚本；本地的真浏览器联调已经起了真服务端",
    "dependency-audit": "要联网查漏洞库，结果随外部数据每天变化",
    "restore-drill": "要 Postgres 与 pg_dump / psql；本地容器里的 Postgres 不保证在跑",
    "postgres-acceptance": "要 Postgres 并起服务进程跑全链路验收；本地只验 SQLite 路径的迁移（migration-drift 的 Postgres 半边同理）",
}


def test_every_ci_job_has_a_local_step_or_a_written_reason():
    import yaml

    jobs = yaml.safe_load(open(os.path.join(ROOT, ".github", "workflows", "ci.yml"), encoding="utf-8"))["jobs"]
    unclassified = sorted(set(jobs) - set(LOCAL_STEPS) - set(CI_ONLY))
    assert not unclassified, f"这些 CI job 本地回归里没有对应的一步，也没写为什么只在 CI 上跑：{unclassified}"
    stale = sorted((set(LOCAL_STEPS) | set(CI_ONLY)) - set(jobs))
    assert not stale, f"CI 里已经没有这些 job，表也要删：{stale}"
    assert not set(LOCAL_STEPS) & set(CI_ONLY)
    src = open(os.path.join(ROOT, "tools", "regress.sh"), encoding="utf-8").read()
    missing = [(job, m) for job, marks in LOCAL_STEPS.items() for m in marks if m not in src]
    assert not missing, f"说了本地有对应步骤，regress.sh 里却找不到：{missing}"
    assert all(len(r) >= 15 for r in CI_ONLY.values()), "只在 CI 上跑要写清理由"
