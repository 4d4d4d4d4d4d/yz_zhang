"""SEC-065 日志不得写入个人信息与凭据（112 号 spec）。

日志会成为第二份个人信息库：它被拷进日志平台、发给外包排障、保留得比业务库还久，
而它从来不在「删除我的数据」的范围里。

量过之后的三个洞（V137 之前）：
1. 一半的日志行**根本没经过脱敏**：uvicorn 自带的访问日志与错误日志走自己的格式，
   访问日志带查询串（`/search?q=…` 的原始搜索词）与客户端 IP；
2. 未处理异常的堆栈由 uvicorn 原样打出，而 SQLAlchemy 异常默认带绑定参数——
   注册撞唯一约束那一次，日志里就是手机号与密码哈希；
3. 我们自己的格式化器把异常堆栈**整个丢掉**（生产出 500 时无从查），
   脱敏只认三种数字，不认 token、Bearer、`password=`、邮箱。

这里的断言跑的是**真进程**：按 Dockerfile 里那条命令起 uvicorn，走一遍会碰到敏感值的路径，
然后逐行读它的 stdout / stderr。
"""
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from app.core import observability as obs

SERVER = Path(__file__).resolve().parents[1]
PHONE = "13900139001"
PASSWORD = "Sup3r-secret-pw!"
SEARCH_PHONE = "13700137007"
EMAIL = "zhang.wei.private@example.com"


def _dockerfile_cmd() -> list[str]:
    text = (SERVER / "Dockerfile").read_text(encoding="utf-8")
    m = re.search(r"^CMD\s+(\[.*\])\s*$", text, re.M)
    assert m, "Dockerfile 里找不到 CMD：这条闸门跑的必须是生产那条命令"
    return json.loads(m.group(1))


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _leaks(text: str, secrets: list[str]) -> list[str]:
    """哪些敏感值原样出现在了日志里。"""
    return [s for s in secrets if s in text]


def test_the_leak_scanner_sees_a_planted_secret():
    """扫描器自检：扫不到等于全绿，是最糟的一种绿。"""
    assert _leaks(f"user {PHONE} logged in", [PHONE]) == [PHONE]
    assert _leaks(obs.redact(f"user {PHONE} logged in"), [PHONE]) == []


@pytest.fixture(scope="module")
def real_server_log():
    """按 Dockerfile 的 CMD 起一个真 uvicorn，走一遍注册 / 登录 / 搜索 / 404，收下全部输出。"""
    cmd = _dockerfile_cmd()
    port = _free_port()
    cmd = [c if c != "0.0.0.0" else "127.0.0.1" for c in cmd]
    cmd[cmd.index("--port") + 1] = str(port)
    tmp = tempfile.mkdtemp()
    env = {**os.environ, "PLATFORM_DATABASE_URL": f"sqlite:///{tmp}/log.db", "PLATFORM_LOG_LEVEL": "INFO",
           "PLATFORM_ENV": "dev", "PYTHONUNBUFFERED": "1"}
    out_path = Path(tmp) / "server.log"
    with open(out_path, "wb") as out:
        proc = subprocess.Popen(cmd, cwd=SERVER, env=env, stdout=out, stderr=subprocess.STDOUT)
        try:
            base = f"http://127.0.0.1:{port}"
            for _ in range(100):
                try:
                    if httpx.get(f"{base}/readyz", timeout=1).status_code < 500:
                        break
                except httpx.HTTPError:
                    time.sleep(0.1)
            api = f"{base}/api/v1"
            r = httpx.post(f"{api}/auth/register", json={"phone": PHONE, "password": PASSWORD,
                                                         "nickname": "日志", "sms_code": "123456"})
            assert r.status_code == 201, r.text
            token = r.json()["token"]
            httpx.post(f"{api}/auth/login", json={"phone": PHONE, "password": PASSWORD})
            httpx.post(f"{api}/auth/login", json={"phone": PHONE, "password": "wrong-" + PASSWORD})
            h = {"Authorization": f"Bearer {token}"}
            httpx.get(f"{api}/search", params={"q": SEARCH_PHONE}, headers=h)
            httpx.get(f"{api}/search", params={"q": EMAIL}, headers=h)
            httpx.get(f"{api}/no-such-path", params={"token": token, "phone": PHONE})
        finally:
            proc.terminate()
            proc.wait(timeout=20)
    return out_path.read_text(encoding="utf-8", errors="replace"), token


def test_every_line_the_production_command_writes_is_structured(real_server_log):
    """一个出口：每一行都是 JSON（因而都过了脱敏），包括 uvicorn 的启动与关闭信息。"""
    text, _ = real_server_log
    lines = [ln for ln in text.splitlines() if ln.strip()]
    assert len(lines) >= 5, f"真进程几乎没写日志，闸门没在测东西：{text[:500]}"
    bad = [ln for ln in lines if not ln.startswith("{")]
    assert not bad, "这些行绕开了结构化与脱敏（uvicorn 自带格式？）：\n" + "\n".join(bad[:8])
    for ln in lines:
        json.loads(ln)


def test_no_credential_or_personal_value_reaches_the_log(real_server_log):
    text, token = real_server_log
    leaked = _leaks(text, [PHONE, PASSWORD, "wrong-" + PASSWORD, SEARCH_PHONE, EMAIL, token,
                           token.split(".")[-1]])
    assert not leaked, f"这些值原样进了日志：{leaked}"


def test_access_lines_carry_the_route_not_the_query_string(real_server_log):
    """V127 定下搜索词是个人信息：访问日志只记路由模板，不记查询串。"""
    text, _ = real_server_log
    access = [json.loads(ln) for ln in text.splitlines() if ln.startswith("{") and '"logger": "access"' in ln]
    assert access, "没有访问日志：ObservabilityMiddleware 没在记？"
    assert all("?" not in a.get("path", "") for a in access)
    # 任何一行（不管哪个 logger）都不许出现查询串：脱敏只认得出手机号这类模式，认不出一个人名搜索词
    assert "search?" not in text and "q=" not in text, "查询串进了日志（uvicorn 的访问日志又开了？）"
    paths = {a.get("path") for a in access}
    assert "/search" in paths, sorted(paths)
    # 没匹配上路由的请求只记一个标签：不许让人用随机 URL 撑爆指标、也不把 URL 原样写进日志
    assert obs.UNMATCHED in paths and not any("no-such-path" in p for p in paths), sorted(paths)


def _capture_root():
    import io
    import logging

    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(obs.JsonFormatter())
    root = logging.getLogger()
    old = root.handlers
    root.handlers = [handler]
    return buf, lambda: setattr(root, "handlers", old)


def test_an_unhandled_500_keeps_its_traceback_but_not_the_sql_parameters(client):
    """堆栈要有（否则生产出事查不了），SQL 参数不能有（否则手机号进日志）。"""
    from app.core.db import engine

    app = client.app

    @app.get("/__probe_500")
    def _boom():
        with engine.begin() as conn:
            conn.execute(sa.text("CREATE TABLE IF NOT EXISTS __probe_u (phone TEXT UNIQUE)"))
            conn.execute(sa.text("DELETE FROM __probe_u"))
            conn.execute(sa.text("INSERT INTO __probe_u VALUES (:p)"), {"p": PHONE})
            conn.execute(sa.text("INSERT INTO __probe_u VALUES (:p)"), {"p": PHONE})

    buf, restore = _capture_root()
    try:
        with TestClient(app, raise_server_exceptions=False) as c:
            assert c.get("/__probe_500").status_code == 500
    finally:
        restore()
    text = buf.getvalue()
    assert PHONE not in text, "撞唯一约束的 500 把手机号带进了日志"
    records = [json.loads(ln) for ln in text.splitlines() if ln.startswith("{")]
    assert any("IntegrityError" in r.get("exc", "") for r in records), "500 的堆栈被丢掉了，生产出事查不了"


@pytest.mark.parametrize("raw, forbidden", [
    ("Authorization: Bearer abc.def.ghi", "abc.def.ghi"),
    ("password=hunter2&next=/", "hunter2"),
    ('{"password": "hunter2", "sms_code": "482913"}', "482913"),
    ("[SQL: INSERT INTO users]\n[parameters: ('13800138000', 'pbkdf2$abc')]\n(Background", "pbkdf2$abc"),
    ("login ok for zhang.wei.private@example.com", "zhang.wei.private"),
    ("id 110101199001011234 verified", "19900101"),
])
def test_redaction_covers_credentials_not_just_three_kinds_of_digits(raw, forbidden):
    assert forbidden not in obs.redact(raw)


def test_redaction_does_not_eat_what_operators_need():
    """脱敏不是把日志变成一片 [redacted]：错误码、状态、业务 id 要留着。"""
    out = obs.redact("task 12345 failed: code=rate_limited status=429")
    assert "12345" in out and "rate_limited" in out and "429" in out


def test_formatter_fails_closed():
    """脱敏本身出错时丢内容，不丢脱敏。"""
    import logging

    class Boom:
        def __str__(self):
            raise RuntimeError(PHONE)

    rec = logging.LogRecord("x", logging.ERROR, __file__, 1, "%s", (Boom(),), None)
    out = obs.JsonFormatter().format(rec)
    assert PHONE not in out and "content dropped" in out


def test_engines_hide_sql_parameters():
    from app.core.db import _make_engine

    assert _make_engine("sqlite:///:memory:").hide_parameters is True
    src = (SERVER / "app" / "core" / "db.py").read_text(encoding="utf-8")
    assert src.count("hide_parameters=True") >= 2, "Postgres 那条分支也要藏参数"


def test_no_print_in_application_code():
    """print 绕开日志出口与脱敏，直接进 stdout。"""
    offenders = []
    for path in (SERVER / "app").rglob("*.py"):
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if re.match(r"\s*print\(", line):
                offenders.append(f"{path.relative_to(SERVER)}:{i}")
    assert not offenders, offenders


if __name__ == "__main__":  # pragma: no cover
    sys.exit(pytest.main([__file__, "-q"]))
