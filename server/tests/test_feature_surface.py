"""FEAT-001 功能面只增不减（用户要求：功能增补兼容原有实现，不删除、不替换删除）。

清单在 `docs/FEATURE-SURFACE.txt`：接口、网页路由、SDK 方法、App 页面模块。
- 清单里的每一项现在都还在；下线的必须进 `RETIRED` 并写理由与替代品；
- 新加的功能要登记进清单（`python -m scripts.feature_surface --write`），清单才不会悄悄过期。
"""
from scripts import feature_surface as fs


def test_nothing_on_the_feature_surface_has_disappeared():
    missing = fs.snapshot() - fs.current() - set(fs.RETIRED)
    assert not missing, ("这些功能曾经在、现在没了（FEAT-001 只增不减）：\n  " + "\n  ".join(sorted(missing))
                         + "\n要么恢复；确需下线，写进 scripts/feature_surface.py 的 RETIRED 并写明理由与替代品。")


def test_new_features_are_registered_in_the_list():
    new = fs.current() - fs.snapshot()
    assert not new, ("新增的功能还没登记进 docs/FEATURE-SURFACE.txt：\n  " + "\n  ".join(sorted(new))
                     + "\n运行 `python -m scripts.feature_surface --write`。")


def test_retired_items_really_are_gone_and_say_what_replaced_them():
    cur = fs.current()
    assert not set(fs.RETIRED) & cur
    assert all("替代" in why and len(why) >= 20 for why in fs.RETIRED.values())


def test_the_scanner_sees_all_four_kinds():
    cur = fs.current()
    for kind, at_least in (("api", 300), ("web", 20), ("sdk", 250), ("app", 10)):
        assert sum(1 for x in cur if x.startswith(kind + " ")) >= at_least, kind
