"""FEAT-001 功能面只增不减：接口、网页路由、SDK 方法、App 页面模块的清单。

用户的要求：「功能增补应该是兼容原有实现，而不是删除原有功能，替换删除」。
光靠记得不够——这里把「功能面」列成一张清单（`docs/FEATURE-SURFACE.txt`），
闸门（`tests/test_feature_surface.py`）核对：清单里的每一项现在都还在；
确需下线的，必须写进 `RETIRED` 并写明理由与替代品。

    python -m scripts.feature_surface --write    # 新增功能后把新项登记进清单
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SNAPSHOT = REPO / "docs" / "FEATURE-SURFACE.txt"

# 下线过的：键 → 理由与替代品。历史扫描（V140，163 个提交）只找到这两处，都是「换了更安全的写法」，功能没少
RETIRED = {
    "api POST /api/v1/users/{user_id}/follow":
        "V117：toggle 双击 / 弱网重试会把刚关注的人取消掉；替代为幂等的 PUT（关注）与 DELETE（取消），两端客户端同批改",
    "sdk addCertification":
        "V82：对服务端永远 422（字段对不上），替代为 submitCertification + myCertifications",
}


def current() -> set[str]:
    sys.path.insert(0, str(REPO / "server"))
    from app.main import app

    out: set[str] = set()
    for path, ops in app.openapi()["paths"].items():
        out.update(f"api {m.upper()} {path}" for m in ops if m in ("get", "post", "put", "patch", "delete"))
    for r in app.routes:   # 不进 OpenAPI 的运维端点（/readyz、/metrics……）
        for m in sorted(getattr(r, "methods", None) or ()):
            if m not in ("HEAD", "OPTIONS"):
                out.add(f"api {m} {r.path}")
    for f in (REPO / "web" / "src").rglob("*.tsx"):
        if ".test." not in f.name:
            out.update(f"web {p}" for p in re.findall(r'path="([^"]+)"', f.read_text(encoding="utf-8")))
    client = (REPO / "packages" / "core" / "src" / "client.ts").read_text(encoding="utf-8")
    out.update(f"sdk {m}" for m in re.findall(r"^  (?:async )?([a-zA-Z][a-zA-Z0-9]*)\(", client, re.M)
               if m != "constructor")
    out.update(f"app {f.stem}" for f in (REPO / "app").glob("*.tsx") if ".test." not in f.name)
    return out


def snapshot() -> set[str]:
    return {line.strip() for line in SNAPSHOT.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")}


def main() -> int:
    if "--write" in sys.argv:
        keep = snapshot() if SNAPSHOT.exists() else set()
        items = sorted(keep | current())
        SNAPSHOT.write_text("# 功能面清单（FEAT-001）：只增不减。下线须进 scripts/feature_surface.py 的 RETIRED 并写理由\n"
                            + "\n".join(items) + "\n", encoding="utf-8")
        print(f"清单 {len(items)} 项")
        return 0
    missing = snapshot() - current() - set(RETIRED)
    print("\n".join(sorted(missing)) or "功能面完整")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
