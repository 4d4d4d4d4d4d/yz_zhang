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
    cfg = json.load(open(os.path.join(ROOT, "app", "package.json"), encoding="utf-8"))["jest"]
    assert "<rootDir>/node_modules" in cfg.get("moduleDirectories", []), \
        "packages/core 的源码在 CI 上向上找不到根 node_modules（App job 只装 app 的依赖）"


def test_esbuild_parse_tests_skip_without_frontend_deps_instead_of_failing():
    for name in ("test_app_parallax.py", "test_app_video_feed.py"):
        src = open(os.path.join(ROOT, "server", "tests", name), encoding="utf-8").read()
        assert 'os.path.join(ROOT, "node_modules", ".bin", "esbuild")' in src, name
