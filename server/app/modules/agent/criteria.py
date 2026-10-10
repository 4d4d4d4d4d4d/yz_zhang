"""AGT-030/031 验收判据：**平台判，不让 agent 自己判卷**。

需求原话是「测试用例通过什么算验收」。这条抓住了 AI 执行任务与人执行任务
最本质的区别：人做的活靠信任与商誉兜底，**AI 做的活只能靠客观判据兜底**。

所以判据的执行必须在平台侧，而且 agent 拿不到判据的实现——它只拿到任务
描述。让执行者自己声明「我通过了验收」，和让它自己声明「我很有信心」
是同一种无效；置信度已经是自报的了，正因为自报才需要一道独立的客观闸门
压在它上面。

判据分两类：

- `auto`   平台执行，**阻断交付**（AGT-031）
- `manual` 人判，不阻断交付，但原样带进验收界面让发布方逐条勾

`manual` 存在的意义是把「怎样算做完」在**开工前**讲清楚——这比事后争议
便宜得多（AIO-001 的判断，从 mission 推广到 task）。
"""
import json
import re

from app.core.errors import bad_request

# 支持的自动判据。**刻意做成一个封闭集合**：
# 判据是平台代替发布方做出的客观承诺，不能让任意表达式混进来
# （一个可以写任意正则的字段，就是一个可以打爆 CPU 的字段）。
AUTO_CHECKS = ("contains", "not_contains", "regex", "min_length", "max_length",
               "is_json", "json_has_keys")

MAX_PATTERN_LEN = 200
MAX_CRITERIA = 20


def validate(criteria: list) -> list:
    """发布时校验验收项结构。**校验放在发布环节**，不放在执行环节——
    一个写错的判据要在开工前就被发现，而不是等 agent 跑完才报错。"""
    if criteria is None:
        return []
    if not isinstance(criteria, list):
        raise bad_request("验收标准必须是列表", "invalid_criteria")
    if len(criteria) > MAX_CRITERIA:
        raise bad_request(f"验收标准最多 {MAX_CRITERIA} 条", "too_many_criteria")
    out = []
    for i, c in enumerate(criteria):
        if not isinstance(c, dict) or not str(c.get("text", "")).strip():
            raise bad_request(f"第 {i + 1} 条验收标准缺少描述", "invalid_criteria")
        kind = c.get("kind", "manual")
        if kind not in ("auto", "manual"):
            raise bad_request(f"第 {i + 1} 条验收标准类型无效", "invalid_criteria")
        item = {"text": str(c["text"])[:200], "kind": kind}
        if kind == "auto":
            check = c.get("check") or {}
            op = check.get("op")
            if op not in AUTO_CHECKS:
                raise bad_request(
                    f"第 {i + 1} 条自动判据不支持「{op}」，可用：{'/'.join(AUTO_CHECKS)}",
                    "unsupported_check",
                )
            value = check.get("value")
            if op in ("contains", "not_contains", "regex") and not isinstance(value, str):
                raise bad_request(f"第 {i + 1} 条判据缺少字符串参数", "invalid_criteria")
            if op == "regex":
                if len(value) > MAX_PATTERN_LEN:
                    raise bad_request("正则判据过长", "invalid_criteria")
                try:
                    re.compile(value)
                except re.error:
                    raise bad_request(f"第 {i + 1} 条判据正则非法", "invalid_criteria")
            if op in ("min_length", "max_length") and not isinstance(value, int):
                raise bad_request(f"第 {i + 1} 条判据参数必须是整数", "invalid_criteria")
            if op == "json_has_keys" and not (
                isinstance(value, list) and all(isinstance(k, str) for k in value)
            ):
                raise bad_request(f"第 {i + 1} 条判据参数必须是字符串列表", "invalid_criteria")
            item["check"] = {"op": op, "value": value}
        out.append(item)
    return out


def _run_auto(op: str, value, output: str) -> tuple[bool, str]:
    if op == "contains":
        return (value in output), f"需包含「{value}」"
    if op == "not_contains":
        return (value not in output), f"不得包含「{value}」"
    if op == "regex":
        # 判据由发布方写、平台执行，长度已在 validate 限过；
        # 这里再兜一次异常，坏正则不该把整次执行打挂
        try:
            return bool(re.search(value, output)), f"需匹配 /{value}/"
        except re.error as exc:
            return False, f"判据正则执行失败：{exc}"
    if op == "min_length":
        return (len(output) >= value), f"长度需 ≥ {value}，实际 {len(output)}"
    if op == "max_length":
        return (len(output) <= value), f"长度需 ≤ {value}，实际 {len(output)}"
    if op == "is_json":
        try:
            json.loads(output)
            return True, "是合法 JSON"
        except Exception:
            return False, "不是合法 JSON"
    if op == "json_has_keys":
        try:
            data = json.loads(output)
        except Exception:
            return False, "不是合法 JSON，无法检查字段"
        if not isinstance(data, dict):
            return False, "JSON 顶层不是对象"
        missing = [k for k in value if k not in data]
        return (not missing), ("字段齐全" if not missing else f"缺少字段：{missing}")
    return False, f"未知判据 {op}"


def evaluate(criteria: list, output: str) -> tuple[list, bool]:
    """逐条判定，返回 (结果列表, 是否全部 auto 项通过)。

    `manual` 项一律记为 `passed=None`——**不猜**。把「还没人判」和
    「判过了没通过」混成同一个 False，验收界面上就分不清该找谁。
    """
    results = []
    all_auto_passed = True
    for c in criteria or []:
        if c.get("kind") != "auto":
            results.append({"text": c.get("text", ""), "kind": "manual",
                            "passed": None, "detail": "待人工确认"})
            continue
        check = c.get("check") or {}
        passed, detail = _run_auto(check.get("op"), check.get("value"), output)
        results.append({"text": c.get("text", ""), "kind": "auto",
                        "passed": passed, "detail": detail})
        if not passed:
            all_auto_passed = False
    return results, all_auto_passed
