import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("PLATFORM_DATABASE_URL", "sqlite:///./test_platform.db")

import pytest
from fastapi.testclient import TestClient

from app.core.db import Base, engine
from app.main import create_app


@pytest.fixture()
def client():
    from app.core.ratelimit import reset

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    reset()  # 限流计数器进程级，测试间清空
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


def verify_user(client, user, name="张三"):
    r = client.post(
        "/api/v1/users/me/verify",
        json={"real_name": name, "id_number": "110101199001011234"},
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
