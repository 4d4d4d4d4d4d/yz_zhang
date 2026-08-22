import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("PLATFORM_DATABASE_URL", "sqlite:///./test_platform.db")
# 测试里访问日志只会淹没失败信息；DEP-040 的脱敏与格式由 test_deployment 直接验证
os.environ.setdefault("PLATFORM_LOG_LEVEL", "WARNING")
# SEC-012 全局写限流是按 IP 的粗粒度兜底；测试里所有请求共享 "testclient" 这一个
# 来源，等价于「几百人挤在同一个 NAT 后面」，会把整套测试误杀。
# 中间件本身的行为由 test_security_hardening 用 monkeypatch 调低阈值单独验证。
os.environ.setdefault("PLATFORM_WRITE_RATE_PER_MINUTE", "100000")

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from app.core.db import Base, engine
from app.main import create_app


@pytest.fixture()
def client():
    from app.core.guard import reset as guard_reset
    from app.core.ratelimit import reset

    Base.metadata.drop_all(engine)
    # 测试库由 create_all 建；若本地残留过 alembic 印记（如手工跑过 upgrade），
    # 会让 /readyz 误报版本不一致，这里一并清掉
    with engine.begin() as conn:
        conn.execute(sa.text("DROP TABLE IF EXISTS alembic_version"))
    Base.metadata.create_all(engine)
    reset()        # 限流计数器进程级，测试间清空
    guard_reset()  # SEC-020 失败计数与 IP 封禁同样进程级：
                   # 否则某个测试的错误登录会把 testclient 这个共享 IP 封掉，
                   # 之后所有测试全挂
    app = create_app()
    with TestClient(app) as c:
        yield c


# ---------- 共享辅助 ----------
def register(client, phone, nickname="", password="pass123456") -> dict:
    r = client.post(
        "/api/v1/auth/register",
        json={"phone": phone, "password": password, "nickname": nickname, "sms_code": "123456"},
    )
    assert r.status_code == 201, r.text
    data = r.json()
    return {"token": data["token"], "id": data["user"]["id"]}


def auth(user) -> dict:
    return {"Authorization": f"Bearer {user['token']}"}


def verify_user(client, user, name="张三", id_number=None):
    """VND-023：证件号一人一号（同号不得绑多账号），故按用户 id 派生唯一证件号。"""
    r = client.post(
        "/api/v1/users/me/verify",
        json={"real_name": name,
              "id_number": id_number or f"11010119900101{user['id']:04d}"},
        headers=auth(user),
    )
    assert r.status_code == 200, r.text


def topup(client, user, amount):
    r = client.post("/api/v1/wallet/topup", json={"amount_cents": amount}, headers=auth(user))
    assert r.status_code == 200, r.text


# OPS-011 内部 job 端点需携带共享密钥（与 settings.JOB_TOKEN 一致）
JOB_HEADERS = {"X-Job-Token": "dev-job-token-change-me"}


def respond_dispute(client, dispute_id, user, content="我方对交付情况作如下说明与举证。"):
    """DSP-005 被诉方答辩：裁决前需保障其陈述机会（两造兼听），测试通用前置。"""
    r = client.post(f"/api/v1/disputes/{dispute_id}/statements",
                    json={"content": content}, headers=auth(user))
    assert r.status_code == 201, r.text


def bind_payout(client, user, holder="张三"):
    """PAY-005 提现前置：绑定收款账户（默认收款人与 verify_user 实名一致）。"""
    r = client.put("/api/v1/wallet/payout-account",
                   json={"kind": "bank", "account_no": "6222020000123456", "holder_name": holder},
                   headers=auth(user))
    assert r.status_code == 200, r.text


@pytest.fixture()
def requester(client):
    user = register(client, "13800000001", "发布者")
    verify_user(client, user)
    return user


@pytest.fixture()
def worker(client):
    user = register(client, "13800000002", "执行者")
    verify_user(client, user, "李四")
    return user
