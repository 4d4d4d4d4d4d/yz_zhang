"""SBX-102/103 端侧隐私沙箱的服务端一侧（128 号 spec）。

沙箱模式开着时，助手类的活在手机上本机做，**原文不上云**。服务端这边做两件事：
1. 这些「把自由文本交给 AI 处理」的接口直接拒绝（客户端本来就不会发；这是给老客户端与绕过客户端的兜底）；
2. 服务端自己替这个人跑的 AI（例行任务、已经建好的使命）不把他的内容交给云端模型，退回模板。

清单与共享 SDK `packages/core/src/sandbox.ts` 的 `CLOUD_AI_ENDPOINTS` 双向一致（闸门 `test_sandbox.py`）。
"""
from __future__ import annotations

API = "/api/v1"
CLOUD_AI_ROUTES: frozenset[tuple[str, str]] = frozenset({
    ("POST", "/workbench/items/{item_id}/breakdown"),
    ("POST", "/notebook/ask"),
    ("POST", "/notebook/notes/{note_id}/extract-todos"),
    ("POST", "/notebook/methods/distill"),
    ("POST", "/packs/{key}/assistants/{akey}/ask"),
    ("POST", "/opc/contract-review"),
    ("POST", "/tasks/{task_id}/decompositions"),
    ("POST", "/decompositions/{dec_id}/expand"),
    ("POST", "/ai/clarify"),
    ("POST", "/agent/tools/{unit_id}/invoke"),
    ("POST", "/support/ask"),
    ("POST", "/legal/ask"),
    ("POST", "/legal/documents"),
    ("POST", "/missions"),
    # AGT-093（154 号 spec）：蒸馏本身不调模型，但编排在沙箱里本来就建不了，同一类一起拦
    ("POST", "/missions/{mission_id}/summary/distill"),
    # XAPP-015（161 号 spec）：一句目标出计划；沙箱里在本机按 `/xapp/catalog` 的规则表出（planXappLocally）
    ("POST", "/xapp/plan"),
})


def in_sandbox(user) -> bool:
    return bool(user is not None and (user.privacy or {}).get("sandbox"))


def check_request(request, user) -> None:
    """在 `get_current_user` 里调用：已经路由完，拿得到路由模板。"""
    if not in_sandbox(user):
        return
    route = request.scope.get("route")
    path = getattr(route, "path", "") or ""
    if path.startswith(API):
        path = path[len(API):]
    if (request.method, path) in CLOUD_AI_ROUTES:
        from app.core.errors import conflict

        raise conflict("隐私沙箱开着：这类助手的活在你手机上本机做，内容不发到云端。要用云端助手，先在「隐私沙箱」里关掉",
                       "sandbox_cloud_ai_blocked")


def gateway_for(db, user_id: int | None):
    """服务端替某人跑模型时用：他开着沙箱就只用模板（不出网），否则用平台配置的网关。"""
    from app.modules.account.models import User
    from app.modules.decompose.llm import TemplateLLM, get_gateway

    if user_id is not None and in_sandbox(db.get(User, user_id)):
        return TemplateLLM()
    return get_gateway()
