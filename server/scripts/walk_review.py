"""功能检视走查（160 号 spec）：对真服务端走一遍 V178~V185 的主要流程。用法：先用 alembic 迁移一个 Postgres 库 live160 并在 8160 起服务，再运行本脚本。"""
import json, subprocess, sys, time, urllib.request, urllib.error

BASE = "http://127.0.0.1:8160"; API = BASE + "/api/v1"
JOB = {"X-Job-Token": "dev-job-token-change-me"}
PSQL = ["psql", "-h", "127.0.0.1", "-p", "55432", "-U", "postgres", "-d", "live160", "-qtAc"]
ok_all = True


def req(method, path, body=None, token="", headers=None, raw=False):
    h = {"Content-Type": "application/json", **(headers or {})}
    if token:
        h["Authorization"] = f"Bearer {token}"
    r = urllib.request.Request(API + path, data=json.dumps(body).encode() if body is not None else None, method=method, headers=h)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            data = resp.read().decode()
            return resp.status, (json.loads(data) if data else {}), dict(resp.headers)
    except urllib.error.HTTPError as e:
        data = e.read().decode()
        return e.code, (json.loads(data) if data else {}), dict(e.headers)


def sql(q):
    return subprocess.run(PSQL + [q], capture_output=True, text=True).stdout.strip()


def step(name, cond, detail=""):
    global ok_all
    ok_all &= bool(cond)
    print(f"  {'✓' if cond else '✗'} {name}{('  ' + str(detail)[:200]) if (detail and not cond) else ''}")


def user(phone, nick, roles=None, city=""):
    s, b, _ = req("POST", "/auth/register", {"phone": phone, "password": "pass123456", "nickname": nick, "sms_code": "123456"})
    assert s == 201, b
    uid, tok = b["user"]["id"], b["token"]
    if roles is not None:
        sql(f"update users set is_admin=true, admin_roles='{json.dumps(roles)}' where id={uid}")
    if city:
        sql(f"update users set city='{city}' where id={uid}")
    return {"id": uid, "token": tok}


def notes(u):
    s, b, _ = req("GET", "/notifications?limit=100", token=u["token"])
    items = b["items"] if isinstance(b, dict) else b
    return items


print("A. 客服工单：提单 → 先回一句 → 主管指派 → 超时升级 → 两端看到进度 → 导出")
asker = user("13900160001", "提问的人")
boss = user("13900160002", "主管", ["super"])
agent = user("13900160003", "客服小王", ["support"])
s, t, _ = req("POST", "/support/tickets", {"subject": "提现三天没到账", "body": "卡尾号 1234"}, asker["token"])
step("提单", s == 201)
tid = t["id"]
s, b, _ = req("POST", f"/admin/tickets/{tid}/reply", {"reply": "在查了，稍等"}, agent["token"])
step("客服先回一句（不结单）", s == 200 and b["status"] == "open" and b["first_response_at"], b)
s, b, _ = req("POST", f"/admin/tickets/{tid}/assign", {"assignee_id": agent["id"]}, boss["token"])
step("主管指派给客服", s == 200 and b["assignee_id"] == agent["id"], b)
s, b, _ = req("POST", f"/admin/tickets/{tid}/assign", {"assignee_id": agent["id"]}, agent["token"])
step("客服不能指派（403）", s == 403, b)
sql(f"update tickets set created_at = now() at time zone 'utc' - interval '50 hours' where id={tid}")
s, b, _ = req("POST", "/admin/jobs/escalate-tickets", headers=JOB)
step("超时任务把它升到第 2 级", s == 200 and tid in b["level2"], b)
s, b, _ = req("GET", "/support/tickets", token=asker["token"])
mine = b[0] if s == 200 and b else {}
step("提单人看到：有人接手、已升级、客服回复", mine.get("claimed") and mine.get("escalation_level") == 2 and mine.get("replies"), mine)
step("提单人收到「已升级给主管」", any(n["title"] == "你的工单已升级给主管" for n in notes(asker)))
s, b, _ = req("GET", "/admin/tickets?sort=urgent", token=agent["token"])
step("工单台按最急排、带等待时长", s == 200 and b and b[0]["id"] == tid and b[0]["waited_hours"] >= 50, b[:1])
s, b, _ = req("GET", "/users/me/export", token=asker["token"])
step("数据导出里有工单与往来", s == 200 and b.get("tickets") and b["tickets"][0]["replies"], b.get("tickets"))

print("B. 全站公告：定向预览 → 发送 → 已读 → 撤回；定时 → 取消")
ops = user("13900160004", "运营", ["ops"])
sh = user("13900160005", "上海的人", city="上海")
s, b, _ = req("POST", "/admin/announcements/preview", {"title": "上海线下见面会", "body": "周六下午", "city": "上海"}, ops["token"])
step("预览按城市算人数", s == 200 and b["audience"] == 1, b)
s, a, _ = req("POST", "/admin/announcements", {"title": "上海线下见面会", "body": "周六下午", "city": "上海"}, ops["token"])
step("发出，只送到上海的人", s == 200 and a["delivered"] == 1 and any(n["title"] == "上海线下见面会" for n in notes(sh))
     and not any(n["title"] == "上海线下见面会" for n in notes(asker)), a)
n = next(n for n in notes(sh) if n["title"] == "上海线下见面会")
req("POST", f"/notifications/{n['id']}/read", token=sh["token"])
s, rows, _ = req("GET", "/admin/announcements", token=ops["token"])
row = next(r for r in rows if r["id"] == a["id"])
step("阅读率 1/1", row["read"] == 1 and row["read_rate"] == 1.0, row)
s, b, _ = req("POST", f"/admin/announcements/{a['id']}/revoke", {"reason": "时间改了"}, ops["token"])
step("撤回后用户那条显示「已撤回」和理由", s == 200 and any(x["title"].startswith("【已撤回】") and "时间改了" in x["body"] for x in notes(sh)), b)
at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 7200))
s, sc, _ = req("POST", "/admin/announcements", {"title": "维护通知", "scheduled_at": at}, ops["token"])
s2, c, _ = req("POST", f"/admin/announcements/{sc['id']}/cancel", {"reason": "改期"}, ops["token"])
step("定时后取消", s == 200 and sc["status"] == "scheduled" and s2 == 200 and c["status"] == "cancelled", (sc, c))

print("C. 开放 API：Key 用量、配额、剩余次数头、CORS 暴露头")
dev = user("13900160006", "开发者")
req("POST", "/users/me/verify", {"real_name": "张三", "id_number": "110101199003076517"}, dev["token"])
s, k, _ = req("POST", "/developer/api-keys", {"name": "集成", "scopes": ["tasks:read"]}, dev["token"])
step("建 Key", s == 201, k)
s, b, h = req("GET", "/open/v1/tasks", headers={"X-API-Key": k.get("key", ""), "Origin": "http://web.example"})
hl = {k.lower() for k in h}
step("开放 API 带剩余次数 / 配额头", s == 200 and {"x-ratelimit-remaining", "x-quota-remaining", "x-account-quota-remaining"} <= hl, h)
step("CORS 暴露了这些头", "X-Total-Count" in h.get("access-control-expose-headers", h.get("Access-Control-Expose-Headers", "")), h)
s, u, _ = req("GET", f"/developer/api-keys/{k['id']}/usage", token=dev["token"])
step("用量页：今天 1 次、账号合计 1 次", s == 200 and u["today_used"] == 1 and u["account_today_used"] == 1, u)

print("D. 审计：哈希链自检与存证锚点")
comp = user("13900160007", "合规", ["compliance"])
s, b, _ = req("POST", "/admin/jobs/anchor-audit-head", headers=JOB)
step("链头写进存证链", s == 200 and b.get("anchored") is True, b)
s, v, _ = req("GET", "/admin/audit-log/verify", token=comp["token"])
step("自检完整且核对了锚点", s == 200 and v["ok"] and v["anchors_checked"] == 1, v)
sql("update admin_audits set detail='改过了' where id=(select min(id) from admin_audits)")
s, v, _ = req("GET", "/admin/audit-log/verify", token=comp["token"])
step("直接改库后自检指出断点", s == 200 and not v["ok"] and v["problems"], v)

print("E. 场景雷达：法律问答答不上的主题（至少 3 人、不存原文）")
for i in range(3):
    u = user(f"1390016001{i}", f"租客{i}")
    req("POST", "/legal/ask", {"question": "房东不退押金还扣房租怎么办"}, u["token"])
s, r, _ = req("GET", "/admin/packs/radar", token=ops["token"])
gap = [x for x in r if x["source"] == "legal_gap"] if s == 200 else []
step("雷达出现「租房买房」", any(x["key"] == "租房买房" and x["people"] == 3 for x in gap), gap)
step("库里没有问题原文", sql("select count(*) from analytics_events where ref_type like '%押金%'") == "0")

print("\n全部通过" if ok_all else "\n有失败项")
sys.exit(0 if ok_all else 1)
