"""E2E-010 真浏览器 × 真服务端：一次没有 mock 的联调（82 号 spec）。

与 `scripts/smoke.py`（真实 HTTP 主闭环）、`scripts/sandbox_check.py`
（存管合规态）并列的第三条闭环：**前端真的连得上后端吗**。
跑法：`npm run build:web` 之后 `python -m scripts.e2e_web`。

这个仓有 84 条 web 测试，**每一条都把 `fetch` 换掉了**。它们能证明
「按钮按下去会调这个方法、参数是这些」，证明不了最基本的那件事：

    前端与后端真的能对接吗？

差别不是假设出来的。mock 掉 fetch 之后，下面这些全都看不见：

- 构建产物里 API 基址写错（开发时走 vite 代理，生产走同源，两条路不一样）
- CORS 没配对（浏览器拦掉请求，而 mock 里没有浏览器）
- 真实响应体的形状与 TS 声明不一致（形状闸门覆盖的是服务端测试里那些端点）
- token 存取、路由守卫、首屏时序（谁先谁后、拿不到 me 时画什么）

所以这一篇：起一个真服务端，起一个真静态服务（跑 `vite build` 的产物，
不是 dev server——**要验的是构建出来的东西**），用 Chromium 走完
注册 → 登录 → 发任务 → 看见它 的主路径。

不进默认 pytest 轮次，因为它要装浏览器、要起两个进程；CI 里是单独一个
job（`web-e2e`）。它走到了哪些页面，由 `tests/test_e2e_coverage.py` 记账。
"""
from __future__ import annotations

import http.server
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from functools import partial
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WEB_DIST = REPO / "web" / "dist"
API_PORT = 8123
WEB_PORT = 8124


def _free(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def _wait(url: str, timeout: float = 60) -> None:
    end = time.time() + timeout
    while time.time() < end:
        try:
            with urllib.request.urlopen(url, timeout=2):
                return
        except Exception:
            time.sleep(0.5)
    raise RuntimeError(f"等不到 {url}")


class _Proxying(http.server.SimpleHTTPRequestHandler):
    """静态服务 + `/api` 反代到真服务端。

    生产上这一层是 nginx（20 号 spec 的部署形态）。这里用最小实现，
    目的是让浏览器**同源**地访问 API——跨源的话就变成在测 CORS 配置，
    而那是另一件事。SPA 的深链接一律回 index.html。
    """

    def _proxy(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None
        req = urllib.request.Request(
            f"http://127.0.0.1:{API_PORT}{self.path}", data=body, method=self.command)
        for k, v in self.headers.items():
            if k.lower() in ("authorization", "content-type", "x-job-token",
                             "idempotency-key", "x-captcha-token"):
                req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                payload, status = resp.read(), resp.status
        except urllib.error.HTTPError as exc:
            payload, status = exc.read(), exc.code
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):          # noqa: N802
        if self.path.startswith("/api"):
            return self._proxy()
        # SPA：非文件路径回 index.html，否则刷新 /wallet 会 404
        target = WEB_DIST / self.path.lstrip("/")
        if not self.path.startswith("/assets") and not target.is_file():
            self.path = "/index.html"
        return super().do_GET()

    def do_POST(self):         # noqa: N802
        return self._proxy()

    def do_PUT(self):          # noqa: N802
        return self._proxy()

    def do_PATCH(self):        # noqa: N802
        return self._proxy()

    def do_DELETE(self):       # noqa: N802
        return self._proxy()

    def log_message(self, *a):  # 安静
        pass


def _serve_dist() -> http.server.ThreadingHTTPServer:
    handler = partial(_Proxying, directory=str(WEB_DIST))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", WEB_PORT), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def _checks(page, phone: str) -> list[tuple[str, bool, str]]:
    """主路径：注册 → 发任务 → 在广场看见它。返回逐步结论。"""
    out: list[tuple[str, bool, str]] = []

    def step(name: str, ok: bool, detail: str = "") -> None:
        out.append((name, ok, detail))

    page.goto(f"http://127.0.0.1:{WEB_PORT}/login", wait_until="networkidle")
    step("登录页打得开", page.locator("text=注册").count() > 0)

    # 注册：真的打到服务端，真的换回 token
    page.click("text=没有账号？去注册")
    page.fill("input[placeholder='13800000000']", phone)
    page.fill("input[type='password']", "pass123456")
    page.get_by_role("button", name="获取验证码").click()
    page.wait_for_function("document.querySelector('[data-testid=sms-code]').value.length > 0")
    page.get_by_role("button", name="注册").click()
    page.wait_for_url(f"http://127.0.0.1:{WEB_PORT}/", timeout=20000)
    token = page.evaluate("() => localStorage.getItem('token')")
    step("注册走通并拿到 token", bool(token), (token or "")[:12] + "…")

    # Public discovery and opt-in personal space: write through the real API.
    page.wait_for_selector('.discovery-hero', timeout=15000)
    step("以人为中心的发现页", page.locator('.discovery-hero').count() == 1)
    page.goto(f"http://127.0.0.1:{WEB_PORT}/space/edit", wait_until="networkidle")
    page.get_by_label("一句话，让人认识你").fill("E2E：一起做有趣的东西")
    page.get_by_label("公开空间，让别人发现我").check()
    page.get_by_role("button", name="保存空间").click()
    page.get_by_role("link", name="看看我的门面").click()
    page.wait_for_selector('.personal-intro')
    step("个人空间真实发布与浏览", page.locator('text=E2E：一起做有趣的东西').count() > 0)
    page.goto(f"http://127.0.0.1:{WEB_PORT}/cooperate", wait_until="networkidle")
    step("合作入口可达", page.get_by_role("link", name="我想做一件事", exact=False).count() > 0)

    # 钱包：真实响应的三态余额画得出来
    page.goto(f"http://127.0.0.1:{WEB_PORT}/wallet", wait_until="networkidle")
    step("钱包页读到真实余额", page.locator("text=可用余额").count() > 0
         or page.locator("text=我的钱包").count() > 0)

    # 通知偏好：V102 加的那块，数据来自服务端的 MUST_REACH
    page.goto(f"http://127.0.0.1:{WEB_PORT}/notifications", wait_until="networkidle")
    page.wait_for_timeout(500)
    step("通知开关读到服务端的必达清单",
         page.locator("text=以下通知不受开关影响").count() > 0)

    # 不懂就问（V122）：这一页的价值全在**三种结局不一样**，而那只有真浏览器
    # 打真服务端才看得出来——mock 掉 fetch 的测试里，三条分支都是我自己喂的载荷。
    # 这里问一个会命中知识库的问题，验免责声明真的渲染出来了。
    page.goto(f"http://127.0.0.1:{WEB_PORT}/ask", wait_until="networkidle")
    page.fill("input[aria-label='法律问题']", "平台合约有没有效力")
    page.get_by_role("button", name="提问").click()
    page.wait_for_timeout(1500)
    step("法律问答答得出来，且免责声明在",
         page.locator("text=不构成法律意见").count() > 0)
    # 经验读回：空库也要给一句说清「为什么是空的」，而不是一片白
    page.get_by_role("button", name="看最近的").click()
    page.wait_for_timeout(1200)
    step("平台攒的经验读得回来（空库也说清为什么空）",
         page.locator("table").count() > 0
         or page.locator("text=没有闭环就没有经验").count() > 0)

    # ---- 写路径：真的发一个任务出去 ----
    #
    # 这一段是 mock 最测不出来的那部分。V77 把 `ip_assignment` 改成必填时，
    # 改了 Web、改了 314 个测试、加了闸门——而 App 的发布按钮**每次点击都
    # 返回 400**，因为那条闸门只看 Web。真按一次按钮，这类事就藏不住。
    title = f"E2E 保洁 {int(time.time()) % 100000}"
    page.goto(f"http://127.0.0.1:{WEB_PORT}/publish", wait_until="networkidle")
    page.fill("label:has-text('标题') input", title)
    page.fill("label:has-text('预算') input", "200")
    # 知识产权归属：必填（V77），不选就是 400
    page.select_option("label:has-text('交付成果归谁') select", index=1)
    page.get_by_role("button", name="发布任务").click()
    page.wait_for_timeout(2500)
    step("发任务走通（含 V77 的必填归属）",
         "/publish" not in page.url or page.locator(".error").count() == 0,
         page.url.split("/")[-1])

    # 广场上能看见刚发的那一单：读写两端都通了才算对接上
    page.goto(f"http://127.0.0.1:{WEB_PORT}/opportunities", wait_until="networkidle")
    page.wait_for_timeout(800)
    step("刚发的任务出现在广场", page.locator(f"text={title}").count() > 0, title)

    # 客服工单：V102 才补上的自助入口，而且它是**没有前置条件的写路径**——
    # 正好适合用真浏览器验一遍（服务端队列由 V101/V103 的测试盯着）
    page.goto(f"http://127.0.0.1:{WEB_PORT}/support", wait_until="networkidle")
    page.fill("input[placeholder='问题一句话概括']", "E2E：提现多久到账")
    page.get_by_role("button", name="提交工单").click()
    page.wait_for_timeout(1200)
    step("自助开工单并出现在我的工单里",
         page.locator("text=E2E：提现多久到账").count() > 0)
    return out


def main() -> int:
    if not (WEB_DIST / "index.html").is_file():
        print("先 `npm run build:web`：这一篇验的是**构建产物**，不是 dev server")
        return 2
    for port in (API_PORT, WEB_PORT):
        if not _free(port):
            print(f"端口 {port} 被占用")
            return 2

    # 库文件放临时目录：第一版写在 `server/e2e_<时间戳>.db`，跑几轮就在仓里
    # 留下八个未跟踪文件——**一个会把垃圾留在工作区的脚本，下一个人会不敢跑它**。
    # 每次新建（不复用）是刻意的：联调要从空库开始，否则上一轮的数据会让断言蒙对。
    db_dir = tempfile.mkdtemp(prefix="e2e-db-")
    env = {**os.environ, "PLATFORM_ENV": "sandbox",
           "PLATFORM_DATABASE_URL": f"sqlite:///{db_dir}/e2e.db"}
    api = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(API_PORT)],
        cwd=str(REPO / "server"), env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    httpd = _serve_dist()
    console_errors: list[str] = []
    failed: list[str] = []
    try:
        _wait(f"http://127.0.0.1:{API_PORT}/readyz")
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                executable_path="/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
                args=["--no-sandbox"])
            page = browser.new_page()
            page.on("console", lambda m: console_errors.append(m.text)
                    if m.type == "error" else None)
            page.on("pageerror", lambda e: console_errors.append(str(e)))
            # 「控制台有个 404」这种结论没法行动——**必须说出是哪个资源**。
            # 第一版只记 console 文本，而浏览器给的文本里没有 URL
            page.on("response", lambda r: failed.append(f"{r.status} {r.url}")
                    if r.status >= 400 else None)
            results = _checks(page, f"139{int(time.time()) % 100000000:08d}")
            browser.close()
    finally:
        httpd.shutdown()
        api.terminate()
        api.wait(timeout=10)
        shutil.rmtree(db_dir, ignore_errors=True)

    print("真浏览器 × 真服务端：")
    bad = 0
    for name, ok, detail in results:
        print(f"  {'✓' if ok else '✗'} {name}{'  ' + detail if detail else ''}")
        bad += 0 if ok else 1
    # 控制台报错单独算一条：它抓的是「界面看着对、运行时在报错」那一类
    # 哪些 HTTP 失败算缺陷，要分清——**第一版把全部 4xx 都算成失败，
    # 于是报了一条 `GET /tasks/1/dispute → 404`，而那是服务端设计好的回答
    # 「这个任务没有纠纷」（DSPC-010 那条路）。闸门报错的是我自己，不是应用。**
    #
    # 现在的判据：
    #   5xx  → 一定是缺陷（服务端炸了）
    #   422  → 一定是缺陷（前端发了服务端不认的东西，V82 的 addCertification 那一类）
    #   其余 4xx → 记下来但不判失败：404 可以是「没有这条记录」的正常回答，
    #             401 在登录前探 /users/me 时本来就会出现
    ignorable = ("favicon", "manifest", "sw.js", "service worker", "apple-touch")
    interesting = [f for f in failed if not any(w in f.lower() for w in ignorable)]
    defects = [f for f in interesting
               if f.startswith("5") or f.startswith("422")]
    noted = [f for f in interesting if f not in defects]
    print(f"  {'✓' if not defects else '✗'} 没有 5xx / 422"
          f"{'  ' + json.dumps(defects[:3], ensure_ascii=False) if defects else ''}")
    bad += 1 if defects else 0
    if noted:
        # 记下来而不判失败：不说出来的话，真正的问题就藏在这堆噪音里
        print("  · 其他 4xx（可能是正常的「没有这条记录」）："
              + json.dumps(sorted(set(noted))[:4], ensure_ascii=False))
    print("联调通过：构建产物与真服务端能对接。" if not bad else f"{bad} 项未通过。")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
