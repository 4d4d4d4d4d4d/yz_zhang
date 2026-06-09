"""Shared test helper enforcing the YAML-driven evaluation contract.

User contract (2026-06-04):
    "每个评估py 要能基于整个仿真架构，而不是数值计算一下，我的理解是
     评估的时候只要改一些配置文件，然后仿真架构会基于这个配置跑出结果"

i.e. an evaluation file must:
  1. Drive baselines/variants through YAML config files only
  2. Use elaborate_and_run / elaborate / compare from npu_sim.evaluation
  3. Never construct hardware modules in Python or call estimate_*
     directly to derive evaluation verdicts.

Use this helper in any evaluation test file's last assertion block to
lock the contract in for future contributors.
"""

from __future__ import annotations

import io
import re
import tokenize
from pathlib import Path

# Module-type names that may not be Python-constructed inside an evaluation.
_BANNED_CTORS = re.compile(
    r"\b(MCU|OGU|TAU|DMA|MTU|AGU|DAGC|DSB|MAC|VAU|AVP|Dummy|Producer|Consumer|Passthrough|Merger)\("
)

# Direct estimate_* calls bypass the simulator and must not appear.
_BANNED_ESTIMATE = re.compile(r"\.estimate_(latency|energy|area)\b")


def assert_evaluation_is_yaml_driven(module_file: str) -> None:
    """Static lint over an evaluation file's source code.

    Strips strings and comments via tokenize so docstrings may reference
    module type names freely.
    """
    src = Path(module_file).read_text()
    tokens = list(tokenize.generate_tokens(io.StringIO(src).readline))
    code_only = "".join(
        t.string for t in tokens
        if t.type not in (tokenize.STRING, tokenize.COMMENT)
    )

    ctor_hits = _BANNED_CTORS.findall(code_only)
    assert ctor_hits == [], (
        f"{module_file}: forbidden Python-side module construction: {ctor_hits}. "
        f"Evaluation must drive everything through YAML + elaborate_and_run."
    )

    est_hits = _BANNED_ESTIMATE.findall(code_only)
    assert est_hits == [], (
        f"{module_file}: forbidden direct .estimate_* calls: {est_hits}. "
        f"Use compare()/run_simulation() metrics instead."
    )
