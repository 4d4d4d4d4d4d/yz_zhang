"""CLI-090（410 号 spec，V437）SDK 方法收了一个类型化的入参对象、请求体却只挑其中几个字段发——新加的字段会被悄悄丢掉。

V435 写测试时撞上：`taskDraftProfile(draft: TaskDraftInput)` 的请求体逐个列字段，`TaskDraftInput` 加了
`task_certs`，类型检查全过，请求里却没有它；服务端收不到，画像的风险提示就少一条。没有一道闸门看得见。

规则：方法签名是 `name(param: SomeInput…)`、`SomeInput` 是 types.ts 里的接口、请求体里用 `param.字段`
逐个取的，接口里每个字段都要在请求体里出现（整个对象展开或原样发出去的不算）。
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CLIENT = REPO / "packages" / "core" / "src" / "client.ts"
TYPES = REPO / "packages" / "core" / "src" / "types.ts"


def _fields(types: str, name: str) -> list[str] | None:
    m = re.search(r"export interface " + name + r"\b[^{]*\{(.*?)\n\}", types, re.S)
    return re.findall(r"^\s+([a-z_][a-z0-9_]*)\??:", m.group(1), re.M) if m else None


def scan(client: str, types: str) -> tuple[list[str], list[str]]:
    """返回（看到的方法，漏发字段的说明）。"""
    seen, problems = [], []
    for m in re.finditer(r"^  ([a-zA-Z]+)\(([a-zA-Z]+): ([A-Z][A-Za-z]+)[^)]*\) \{\n(.*?)\n  \}", client, re.S | re.M):
        meth, param, typ, body = m.groups()
        fields = _fields(types, typ)
        if not fields:
            continue
        if re.search(r"\.\.\.\s*" + param + r"\b", body) or re.search(r"'(POST|PUT|PATCH)'[^;]*,\s*" + param + r"\s*[,)]", body):
            continue                      # 整个对象发出去：不会丢
        used = set(re.findall(param + r"\.([a-z_][a-z0-9_]*)", body))
        if not used:
            continue
        seen.append(meth)
        missing = [f for f in fields if f not in used]
        if missing:
            problems.append(f"{meth}({param}: {typ}) 的请求体没发 {missing}：类型里有、请求里没有，服务端收不到")
    return seen, problems


def test_cli090_scanner_sees_the_field_by_field_methods():
    seen, _ = scan(CLIENT.read_text(encoding="utf-8"), TYPES.read_text(encoding="utf-8"))
    assert {"taskDraftProfile", "createNote", "addOpcEntry"} <= set(seen), seen


def test_cli090_typed_inputs_are_sent_in_full():
    _, problems = scan(CLIENT.read_text(encoding="utf-8"), TYPES.read_text(encoding="utf-8"))
    assert not problems, "\n  ".join(["SDK 请求体漏发入参字段："] + problems)


def test_cli090_the_scanner_catches_a_dropped_field():
    """闸门自己的红验：少发一个字段要报，整个对象展开不报。"""
    types = "export interface DemoInput {\n  a: string;\n  b?: number;\n}\n"
    dropped = "  demo(x: DemoInput) {\n    return this.request('POST', '/demo', { a: x.a });\n  }\n"
    spread = "  demo(x: DemoInput) {\n    return this.request('POST', '/demo', { ...x });\n  }\n"
    assert scan(dropped, types)[1] and "['b']" in scan(dropped, types)[1][0]
    assert scan(spread, types) == ([], [])
