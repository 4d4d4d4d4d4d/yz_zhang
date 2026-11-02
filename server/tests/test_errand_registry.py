"""SCN-248 发单拦截类别登记一致性（354 号 spec，V381）。

V369、V371、V378 三次加拦截类别，都靠手工同步四处：错误码、i18n 文案、复核类别名、SDK 的可复核清单。
漏一处的后果：拦下后客户端不显示「申请人工复核」，或者复核列表里显示代码、或者错误提示变成英文代码。
这里逐一核对，新加一类漏登记任何一处都会红。
"""
import inspect
import re
from pathlib import Path

import pytest

from app.modules.task import errand
from app.modules.task.errand_reviews import KIND_LABEL

ROOT = Path(__file__).resolve().parents[2]
I18N = (ROOT / "packages/core/src/i18n.ts").read_text(encoding="utf-8")
SDK = (ROOT / "packages/core/src/errandReview.ts").read_text(encoding="utf-8")


def _returned_kinds() -> set[str]:
    return set(re.findall(r'return "(\w+)"', inspect.getsource(errand.restricted_errand)))


def _sdk_codes() -> set[str]:
    block = re.search(r"ERRAND_REVIEW_CODES = \[(.*?)\] as const", SDK, re.S).group(1)
    return set(re.findall(r"'(\w+)'", block))


def test_every_kind_the_guard_can_return_is_registered():
    kinds = _returned_kinds()
    assert len(kinds) >= 9, kinds
    assert kinds == set(errand.KIND_CODES), {"未登记": kinds - set(errand.KIND_CODES), "多登记": set(errand.KIND_CODES) - kinds}


@pytest.mark.parametrize("kind", sorted(errand.KIND_CODES))
def test_each_kind_raises_its_registered_code_with_a_review_hint(kind):
    with pytest.raises(Exception) as e:
        errand._raise_for(kind)
    assert e.value.detail["code"] == errand.KIND_CODES[kind]


@pytest.mark.parametrize("kind", sorted(errand.KIND_CODES))
def test_each_kind_has_a_review_label(kind):
    assert KIND_LABEL.get(kind), f"{kind} 没有复核类别名：复核列表会显示代码"


@pytest.mark.parametrize("code", sorted(set(errand.KIND_CODES.values())))
def test_each_code_has_i18n_and_is_reviewable_in_the_sdk(code):
    assert re.search(rf"^\s*{code}:\s*'", I18N, re.M), f"{code} 没有 i18n 文案"
    assert code in _sdk_codes(), f"{code} 不在 SDK 的 ERRAND_REVIEW_CODES：被拦下后客户端不显示「申请人工复核」"


def test_sdk_lists_no_codes_the_guard_never_raises():
    extra = _sdk_codes() - set(errand.KIND_CODES.values())
    assert not extra, f"SDK 里多出的可复核错误码：{extra}"
