"""STUB-040 沙箱合规态自检：把全部沙箱桩装上，跑一遍完整闭环。

与 `scripts/smoke.py` 的区别：
  smoke.py        跑**开发态**（mock 支付 + 平台内账本），验证「代码能跑」
  sandbox_check   跑**合规态**（存管 + 可靠签名 + 第三方存证），
                  验证「接入真实供应商后该看到的样子」

因此这个脚本也是**对接验收脚本**：真实供应商实现同一组方法后，
把 provider 名换掉再跑一遍，全绿就说明契约对齐了。

    python -m scripts.sandbox_check
"""
import os
import sys

# 必须在导入 app 之前设好：配置在模块加载时求值
os.environ.setdefault("PLATFORM_DATABASE_URL", "sqlite:///./sandbox_check.db")
os.environ["PLATFORM_PAYMENT_PROVIDER"] = "sandbox"
os.environ["PLATFORM_SMS_PROVIDER"] = "sandbox"
os.environ["PLATFORM_KYC_PROVIDER"] = "sandbox"
os.environ["PLATFORM_MODERATION_PROVIDER"] = "sandbox"
os.environ["PLATFORM_STORAGE_PROVIDER"] = "sandbox"
os.environ["PLATFORM_LEDGER_BACKEND"] = "custody"
os.environ["PLATFORM_SIGNATURE_PROVIDER"] = "sandbox-ca"
os.environ["PLATFORM_NOTARY_PROVIDER"] = "sandbox-notary"
os.environ.setdefault("PLATFORM_LOG_LEVEL", "WARNING")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402

from app.core.db import Base, engine  # noqa: E402
from app.main import create_app  # noqa: E402

PASSED = 0


def step(name: str, ok: bool, detail="") -> None:
    global PASSED
    text = str(detail)
    if len(text) > 240:
        text = text[:240] + "…"
    print(f"  {'✓' if ok else '✗'} {name}{'  ' + text if text else ''}")
    if not ok:
        sys.exit(1)
    PASSED += 1


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def register(client, phone: str, nickname: str) -> dict:
    """STUB-055 沙箱短信不回显验证码 → 必须先请求验证码，走严格路径。"""
    r = client.post("/api/v1/auth/send-code", json={"phone": phone})
    assert r.status_code == 200, r.text
    assert "dev_code" not in r.json(), "沙箱短信不得回显验证码"
    from app.vendors.registry import get_provider

    code = get_provider("sms").sent[phone]
    r = client.post("/api/v1/auth/register",
                    json={"phone": phone, "password": "sandbox123456",
                          "nickname": nickname, "sms_code": code})
    assert r.status_code == 201, r.text
    body = r.json()
    return {"token": body["token"], "id": body["user"]["id"]}


def main() -> None:
    print("沙箱合规态自检（存管 + 可靠签名 + 第三方存证）")
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    app = create_app()

    with TestClient(app) as client:
        body = client.get("/version").json()
        step("配置为存管模式", body["ledger_backend"] == "custody", body["ledger_backend"])
        step("沙箱标识为 false（存管形态）", body["sandbox"] is False)

        requester = register(client, "18600000001", "沙箱发布方")
        worker = register(client, "18600000002", "沙箱执行方")
        step("严格短信路径注册成功（未回显验证码）", True)

        for who, uid in ((requester, requester["id"]), (worker, worker["id"])):
            r = client.post("/api/v1/users/me/verify",
                            json={"real_name": "沙箱用户",
                                  "id_number": f"11010119900101{uid:04d}"},
                            headers=auth(who["token"]))
            assert r.status_code == 200, r.text
        step("沙箱 eKYC 通过", True)

        r = client.post("/api/v1/users/me/verify",
                        json={"real_name": "转人工", "id_number": "110101199001019999"},
                        headers=auth(register(client, "18600000003", "人工复核")["token"]))
        step("STUB-056 eKYC manual 三态可达",
             r.status_code == 200 and r.json().get("status") == "manual_review", r.json())

        r = client.post("/api/v1/wallet/topup", json={"amount_cents": 100000},
                        headers=auth(requester["token"]))
        step("充值（付款进存管专户）", r.status_code == 200 and r.json()["status"] == "succeeded")

        from app.vendors.sandbox import BOOK, ESCROW_ACCOUNT

        step("存管专户确实收到钱（钱不经过平台）",
             BOOK.balances.get(ESCROW_ACCOUNT, 0) == 100000,
             f"{ESCROW_ACCOUNT}={BOOK.balances.get(ESCROW_ACCOUNT, 0)}")

        r = client.post("/api/v1/tasks",
                        json={"title": "沙箱验收任务", "description": "合规态闭环自检",
                              "category": "跑腿", "budget_cents": 30000,
                              "city": "杭州", "lat": 30.27, "lng": 120.15,
                              "address_hint": "西湖区"},
                        headers=auth(requester["token"]))
        step("发布任务", r.status_code == 201, r.json() if r.status_code != 201 else r.json()["id"])
        task = r.json()

        r = client.post(f"/api/v1/tasks/{task['id']}/applications",
                        json={"message": "我来"}, headers=auth(worker["token"]))
        app_id = r.json()["id"]
        cid = client.post(f"/api/v1/applications/{app_id}/accept",
                          headers=auth(requester["token"])).json()["contract_id"]
        for u in (requester, worker):
            r = client.post(f"/api/v1/contracts/{cid}/sign", headers=auth(u["token"]))
            assert r.status_code == 200, r.text
        step("双方签署", True)

        sigs = client.get(f"/api/v1/contracts/{cid}/signatures",
                          headers=auth(requester["token"])).json()
        step("STUB-053 签名为可靠电子签名",
             all(s["reliability"] == "qualified" for s in sigs["signatures"]))
        step("证明力声明已升级", "构成可靠电子签名" in sigs["reliability_note"])
        step("签名校验通过", sigs["valid"] is True)

        r = client.post(f"/api/v1/contracts/{cid}/fund", headers=auth(requester["token"]))
        step("托管资金", r.status_code == 200, r.text if r.status_code != 200 else "")
        client.post(f"/api/v1/tasks/{task['id']}/deliver", headers=auth(worker["token"]))
        r = client.post(f"/api/v1/tasks/{task['id']}/accept-delivery",
                        headers=auth(requester["token"]))
        step("验收放款", r.status_code == 200, r.text if r.status_code != 200 else "")

        body = client.get(f"/api/v1/contracts/{cid}/settlements",
                          headers=auth(requester["token"])).json()
        orders = body["settlements"]
        step("STUB-050 产生分账指令", len(orders) == 1, f"{len(orders)} 条")
        order = orders[0]
        step("指令由存管方执行", order["backend"] == "custody", order["backend"])
        step("指令带存管流水号", bool(order["custody_ref"]), order["custody_ref"])
        step("分账守恒", sum(s["amount_cents"] for s in order["splits"]) == order["total_cents"])
        step("存管账簿收到分账",
             BOOK.balances.get(f"custody:user:{worker['id']}", 0) > 0,
             {k: v for k, v in BOOK.balances.items() if v})

        r = client.post("/api/v1/anchors/jobs/notarize",
                        headers={"X-Job-Token": "dev-job-token-change-me"})
        step("STUB-054 第三方存证已背书", r.json().get("backed") is True, r.json())
        cov = client.get("/api/v1/anchors/coverage").json()
        step("存证覆盖全量", cov["uncovered_entries"] == 0, cov["note"])

        from app.core.db import SessionLocal
        from app.modules.risk import service as risk

        with SessionLocal() as db:
            recon = risk.reconcile(db)
        step("资金四不变量成立", recon["ok"] is True, recon.get("mismatches"))

    print(f"\n沙箱合规态自检通过（{PASSED} 项）。")
    print("接真实供应商后把 provider 名换掉再跑一遍，全绿即说明契约对齐。")


if __name__ == "__main__":
    main()
