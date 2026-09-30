"""E2E-011 联调脚本覆盖了哪些页面（82 号 spec）。

`scripts/e2e_web.py` 本身要在 CI 里跑（真服务端 + 真构建产物 + Chromium），
而这一篇是它的**账**：新加一个页面，要么被联调走到，要么在豁免表里写理由。

为什么需要这张账：84 条 web 测试全都 mock 了 fetch，所以「这个页面真的
连得上后端吗」这个问题，只有联调脚本能回答。页面加了而联调没走到，
那个页面就回到了「只有 mock 证明过」的状态——而这一路反复证明，
mock 证明不了的那一半才是出事的那一半。
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
E2E = REPO / "server" / "scripts" / "e2e_web.py"
APP_TSX = REPO / "web" / "src" / "App.tsx"

# 联调**刻意不走**的页面 -> 为什么。值是理由，不是布尔（V90 那条）。
E2E_EXEMPT: dict[str, str] = {
    "/admin": "要管理员账号与一整套运营数据；管理后台由 76 号的覆盖闸门与 11 条 web 测试盯着",
    "/verify": "核验台要先有核验单，而核验单要先有 agent 任务——建这套前置比这条断言本身贵",
    "/publish": "已经走到了（发任务那一步），这里列出来只是说明它不在「未覆盖」里",
    "/messages": "站内信要两个用户对话，联调是单用户脚本；IM 由服务端测试覆盖",
    "/circles": "圈层是内容侧功能，不在「钱与权利」的主路径上",
    "/community": "同上：内容消费，出问题不卡任何人的钱",
    "/rewards": "优惠券要先有活动数据，运营侧配置",
    "/teams": "团队要先建团队与成员，且审批闭环由服务端测试覆盖",
    "/ventures": "合作体要先有份额与贡献记录，前置比断言本身贵；份额与分配由服务端测试覆盖",
    "/developer": "开发者设置（API Key / Webhook）面向少数用户，且有服务端测试",
    "/tasks/:id": "任务详情要先有一单在途；主路径里已经走到了广场上的那一单",
    "/login": "已经走到了（注册就是在这一页）",
    "/profile": "个人资料页的读写由 web 测试覆盖，联调里没有它独有的后端契约",
}


def _routes() -> set[str]:
    """从 App.tsx 的路由表里取出页面路径——**不手抄**。"""
    src = APP_TSX.read_text(encoding="utf-8")
    out = set()
    for m in re.finditer(r'<Route\s+path="([^"]+)"', src):
        path = m.group(1)
        if path in ("*", "/"):
            continue
        out.add(path if path.startswith("/") else "/" + path)
    return out


def _e2e_visited() -> set[str]:
    """联调脚本里 `page.goto(...)` 走过的路径。"""
    src = E2E.read_text(encoding="utf-8")
    out = {"/"}
    for m in re.finditer(r'WEB_PORT\}(/[\w/:-]*)"', src):
        out.add(m.group(1) or "/")
    return out


def test_e2e011_scanner_finds_routes_and_visits():
    """扫不到等于全绿，是最糟的一种绿。"""
    routes, visited = _routes(), _e2e_visited()
    assert len(routes) >= 10, f"只扫到 {len(routes)} 条路由，提取逻辑可能坏了"
    assert len(visited) >= 4, f"只扫到 {len(visited)} 个联调访问，提取逻辑可能坏了"
    for known in ("/wallet", "/notifications"):
        assert known in visited, f"联调明明走了 {known}，扫描却说没有"


def test_e2e011_every_page_is_visited_or_exempt():
    """新加页面要么被联调走到，要么写明为什么不走。"""
    routes = _routes()
    visited = _e2e_visited()
    missing = sorted(r for r in routes if r not in visited and r not in E2E_EXEMPT)
    assert not missing, (
        "这些页面联调没走到、也没写豁免理由：\n  " + "\n  ".join(missing)
        + "\n走一趟，或者在 E2E_EXEMPT 里写清为什么不走（一句人话）。"
    )


def test_e2e011_exempt_table_is_honest():
    """豁免理由不许是「还没做」——那是欠账，归 72 号台账。"""
    routes = _routes()
    stale = sorted(r for r in E2E_EXEMPT if r not in routes)
    assert not stale, f"豁免表里这些路由已经不在 App.tsx 里了：{stale}"
    for path, why in sorted(E2E_EXEMPT.items()):
        assert len(why) >= 12, f"{path} 的豁免理由太短：{why}"
        for excuse in ("还没做", "待补", "TODO", "以后"):
            assert excuse not in why, f"{path} 的理由是欠账不是理由：{why}"


def test_e2e011_script_checks_the_money_and_rights_paths():
    """联调必须走到「钱与权利」那几步，而不是只打开首页。

    这一条防的是**联调被削成一个健康检查**：`goto('/')` 看见标题就算过，
    那和 `curl /readyz` 没有区别。
    """
    src = E2E.read_text(encoding="utf-8")
    for must in ("注册", "token", "发任务", "广场", "钱包"):
        assert must in src, f"联调脚本里没有「{must}」那一步"
    # 失败判据也要在：只打印不判失败的脚本，CI 里永远是绿的
    assert "return 1 if bad else 0" in src, "脚本不会以非零退出——CI 里它永远绿"
    assert "5xx" in src or "422" in src, "没有对 HTTP 失败下判断"
