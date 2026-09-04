"""演示数据脚本：一键生成可交互的样例数据，方便本地体验主闭环。

用法（server 目录下）：
    python -m scripts.seed_demo
生成后即可用手机号 + 密码 pass123456 登录（验证码固定 123456）。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import create_app  # noqa: E402

API = "/api/v1"


def _register(c, phone, nickname, pwd="pass123456"):
    r = c.post(f"{API}/auth/register",
               json={"phone": phone, "password": pwd, "nickname": nickname, "sms_code": "123456"})
    if r.status_code == 409:  # 已存在则登录
        r = c.post(f"{API}/auth/login", json={"phone": phone, "password": pwd})
    tok = r.json()["token"]
    h = {"Authorization": f"Bearer {tok}"}
    c.post(f"{API}/users/me/verify",
           json={"real_name": nickname, "id_number": "110101199001011234"}, headers=h)
    return h


def main():
    app = create_app()
    with TestClient(app) as c:
        boss = _register(c, "13900010001", "创业者老王")
        cleaner = _register(c, "13900010002", "保洁小美")
        coder = _register(c, "13900010003", "程序员小刚")

        c.patch(f"{API}/users/me", json={"skills": ["保洁", "收纳"], "city": "上海",
                                          "lat": 31.23, "lng": 121.47,
                                          "service_rate_cents": 8000}, headers=cleaner)
        c.patch(f"{API}/users/me", json={"skills": ["前端开发", "后端开发"], "city": "上海"},
                headers=coder)

        c.post(f"{API}/wallet/topup", json={"amount_cents": 500000}, headers=boss)

        # 若干公开任务
        for title, cat, budget in [
            ("周末深度保洁（两室一厅）", "保洁", 25000),
            ("帮取快递到浦东", "跑腿", 3000),
            ("公司官网开发", "软件开发", 800000),
        ]:
            c.post(f"{API}/tasks", json={
                "title": title, "category": cat, "budget_cents": budget,
                "is_remote": cat == "软件开发", "city": "上海",
                "lat": 31.2304, "lng": 121.4737, "address_hint": "静安寺商圈",
                "address_exact": "静安区南京西路 1234 号",
            }, headers=boss)

        # 一条已闭环任务，产生知识库与评价数据
        r = c.post(f"{API}/tasks", json={
            "title": "样板间保洁", "category": "保洁", "budget_cents": 20000,
            "city": "上海", "lat": 31.23, "lng": 121.47, "address_hint": "样板间",
        }, headers=boss)
        tid = r.json()["id"]
        app_id = c.post(f"{API}/tasks/{tid}/applications", json={}, headers=cleaner).json()["id"]
        cid = c.post(f"{API}/applications/{app_id}/accept", headers=boss).json()["contract_id"]
        for h in (boss, cleaner):
            c.post(f"{API}/contracts/{cid}/sign", headers=h)
        c.post(f"{API}/contracts/{cid}/fund", headers=boss)
        c.post(f"{API}/tasks/{tid}/deliver", headers=cleaner)
        c.post(f"{API}/tasks/{tid}/accept-delivery", headers=boss)
        c.post(f"{API}/tasks/{tid}/reviews", json={"stars": 5, "comment": "非常干净"}, headers=boss)

        # 一个圈层 + 一条动态
        circle = c.post(f"{API}/circles", json={"name": "上海保洁互助圈", "kind": "skill",
                                                 "skill_tag": "保洁"}, headers=cleaner).json()
        c.post(f"{API}/circles/{circle['id']}/join", headers=boss)
        c.post(f"{API}/contents", json={"body": "分享一个厨房去油污的小技巧～", "tags": ["保洁"],
                                         "linked_category": "保洁"}, headers=cleaner)

    print("演示数据已生成。登录账号（密码 pass123456）：")
    print("  13900010001 创业者老王（发布者，钱包已充值）")
    print("  13900010002 保洁小美（执行者，有技能与好评）")
    print("  13900010003 程序员小刚（执行者）")


if __name__ == "__main__":
    main()
