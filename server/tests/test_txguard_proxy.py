"""TEST-090（434 号 spec）供应商代理 Guarded 写能转发，删也要转发。

pytest 9.2 起 monkeypatch 对实例记旧值改读实例的 `__dict__`：Guarded 用 __slots__、没有自己的 `__dict__`，
读到的是被代理对象的，里面没有类上定义的方法，于是记成「原来没有」，撤销时对代理做 delattr。
以前代理只转发 setattr 不转发 delattr，测试本身过了、收尾报「'Guarded' object has no attribute」。
"""
import pytest

from app.core.txguard import Guarded


class _Inner:
    in_process = True          # 进程内实现：方法直接返回，不过事务检查

    def verify(self):
        return "real"


def test_delete_goes_through_to_the_wrapped_object():
    inner = _Inner()
    g = Guarded("fake", inner)
    g.extra = 1
    assert inner.extra == 1
    del g.extra
    assert not hasattr(inner, "extra")


def test_monkeypatching_a_method_on_the_proxy_is_undone_cleanly():
    inner = _Inner()
    g = Guarded("fake", inner)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(g, "verify", lambda: "patched")
        assert g.verify() == "patched"
    assert g.verify() == "real" and "verify" not in vars(inner)
