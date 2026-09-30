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

# IPC-010 起发任务必须声明知识产权归属。这个脚本漏了它，于是**四条任务
# 全部 400**，而脚本一路不看状态码，直到第 64 行才以 `KeyError: 'id'` 崩掉。
# README 让新来的人第一件事就跑它——一个新人看到的第一个输出是 KeyError。
IP_ASSIGNMENT = "assign"


def _ok(r, what: str):
    """每一步都看状态码。

    原来这个脚本**一次都不看**：任务创建失败三次也照样往下走，
    错误在三十行之后以 `KeyError: 'id'` 的形式出现——那个位置离病因太远，
    读栈的人会去查 `/applications`，而坏的是 `/tasks`。
    **在出错的那一行报错，是脚本对读它的人最基本的礼貌。**
    """
    if r.status_code >= 400:
        raise SystemExit(f"{what} 失败：HTTP {r.status_code} {r.text[:300]}")
    return r


# 每个人一个证件号：原来三个人共用 110101199001011234，而平台后来加了
# **一人多号**检测（同一证件号只能绑一个账号），于是第二、第三个人的实名
# 静默 409 —— 他们因此报不了名，闭环那一段的数据一条都生成不出来。
# 而 `/users/me/verify` 的返回当时也没人看。
ID_NUMBERS = {
    "13900010001": "110101199001011234",
    "13900010002": "110101199203054028",
    "13900010003": "110101198807122019",
}


def _register(c, phone, nickname, pwd="pass123456"):
    r = c.post(f"{API}/auth/register",
               json={"phone": phone, "password": pwd, "nickname": nickname, "sms_code": "123456"})
    if r.status_code == 409:  # 已存在则登录
        r = c.post(f"{API}/auth/login", json={"phone": phone, "password": pwd})
    _ok(r, f"注册/登录 {nickname}")
    tok = r.json()["token"]
    h = {"Authorization": f"Bearer {tok}"}
    _ok(c.post(f"{API}/users/me/verify",
               json={"real_name": nickname, "id_number": ID_NUMBERS[phone]}, headers=h),
        f"{nickname} 实名认证")
    return h


def main():
    app = create_app()
    with TestClient(app) as c:
        # 这个脚本的目标状态是「演示数据存在」，所以已经存在就直接说清楚。
        #
        # 为什么不做成「可反复追加」：追加一遍就多四条任务、多一份合约，
        # 圈层名还会撞（`name_taken`）——**一个跑两次就得到一份说不清的数据集
        # 的演示脚本，比拒绝跑更糟**。要重来就删库，这句话直接写给用户。
        if c.post(f"{API}/auth/login",
                  json={"phone": "13900010001", "password": "pass123456"}).status_code == 200:
            print("演示数据已存在（13900010001 / pass123456）。")
            print("要重新生成：删掉库文件（或换 PLATFORM_DATABASE_URL）后再跑。")
            return

        boss = _register(c, "13900010001", "创业者老王")
        cleaner = _register(c, "13900010002", "保洁小美")
        coder = _register(c, "13900010003", "程序员小刚")

        c.patch(f"{API}/users/me", json={"skills": ["保洁", "收纳"], "city": "上海",
                                          "lat": 31.23, "lng": 121.47,
                                          "service_rate_cents": 8000}, headers=cleaner)
        c.patch(f"{API}/users/me", json={"skills": ["前端开发", "后端开发"], "city": "上海"},
                headers=coder)

        _ok(c.post(f"{API}/wallet/topup", json={"amount_cents": 500000}, headers=boss), "充值")

        # 若干公开任务
        for title, cat, budget in [
            ("周末深度保洁（两室一厅）", "保洁", 25000),
            ("帮取快递到浦东", "跑腿", 3000),
            ("公司官网开发", "软件开发", 800000),
        ]:
            _ok(c.post(f"{API}/tasks", json={
                "title": title, "category": cat, "budget_cents": budget,
                "is_remote": cat == "软件开发", "city": "上海",
                "lat": 31.2304, "lng": 121.4737, "address_hint": "静安寺商圈",
                "address_exact": "静安区南京西路 1234 号",
                "ip_assignment": IP_ASSIGNMENT,
            }, headers=boss), f"发布任务「{title}」")

        # 一条已闭环任务，产生知识库与评价数据
        r = _ok(c.post(f"{API}/tasks", json={
            "title": "样板间保洁", "category": "保洁", "budget_cents": 20000,
            "city": "上海", "lat": 31.23, "lng": 121.47, "address_hint": "样板间",
            "ip_assignment": IP_ASSIGNMENT,
        }, headers=boss), "发布闭环样例任务")
        tid = r.json()["id"]
        app_id = _ok(c.post(f"{API}/tasks/{tid}/applications", json={}, headers=cleaner),
                     "报名").json()["id"]
        cid = _ok(c.post(f"{API}/applications/{app_id}/accept", headers=boss),
                  "选人成交").json()["contract_id"]
        for h in (boss, cleaner):
            _ok(c.post(f"{API}/contracts/{cid}/sign", headers=h), "签署合约")
        _ok(c.post(f"{API}/contracts/{cid}/fund", headers=boss), "托管资金")
        _ok(c.post(f"{API}/tasks/{tid}/deliver", headers=cleaner), "提交交付")
        _ok(c.post(f"{API}/tasks/{tid}/accept-delivery", headers=boss), "验收放款")
        _ok(c.post(f"{API}/tasks/{tid}/reviews", json={"stars": 5, "comment": "非常干净"},
                   headers=boss), "评价")

        # 一个圈层 + 一条动态
        circle = _ok(c.post(f"{API}/circles", json={"name": "上海保洁互助圈", "kind": "skill",
                                                    "skill_tag": "保洁"}, headers=cleaner),
                     "建圈层").json()
        _ok(c.post(f"{API}/circles/{circle['id']}/join", headers=boss), "加入圈层")
        _ok(c.post(f"{API}/contents", json={"body": "分享一个厨房去油污的小技巧～",
                                            "tags": ["保洁"], "linked_category": "保洁"},
                   headers=cleaner), "发动态")

    print("演示数据已生成。登录账号（密码 pass123456）：")
    print("  13900010001 创业者老王（发布者，钱包已充值）")
    print("  13900010002 保洁小美（执行者，有技能与好评）")
    print("  13900010003 程序员小刚（执行者）")


if __name__ == "__main__":
    main()
