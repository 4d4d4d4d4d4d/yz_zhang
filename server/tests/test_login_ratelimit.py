"""ACC-002 密码登录防暴力破解：同手机号短时间高频尝试限流。

原实现只对注册/短信登录限流，密码登录 /auth/login 完全不限——
攻击者可对已知手机号无限撞库。补齐后：同号 60s 内第 6 次尝试被限流。
"""
from .conftest import register


def test_password_login_brute_force_rate_limited(client):
    register(client, "29000000001", "受害者")  # 真实密码 pass123456

    limited = False
    for i in range(8):
        r = client.post("/api/v1/auth/login",
                        json={"phone": "29000000001", "password": f"guess{i}"})
        if r.status_code == 400 and r.json()["detail"]["code"] == "rate_limited":
            limited = True
            break
    assert limited, "密码登录未触发限流，存在无限撞库风险"


def test_rate_limit_is_per_phone(client):
    register(client, "29000000010", "甲")
    register(client, "29000000011", "乙")
    # 打满甲的额度
    for i in range(6):
        client.post("/api/v1/auth/login",
                    json={"phone": "29000000010", "password": f"x{i}"})
    # 乙不受影响，正确密码可登录
    r = client.post("/api/v1/auth/login",
                    json={"phone": "29000000011", "password": "pass123456"})
    assert r.status_code == 200
