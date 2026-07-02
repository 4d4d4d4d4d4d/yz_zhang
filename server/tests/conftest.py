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
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
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
