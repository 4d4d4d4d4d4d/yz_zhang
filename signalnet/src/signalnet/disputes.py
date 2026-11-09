"""原创申诉与举报（L2 层）。

- appeal（原创申诉）：原作者认为 target 搬运了 original（REQ-OR-004）
- report（举报）：任何人举报 target 为搬运，成立可获赏金（REQ-OR-005）

裁定：陪审按 sqrt(声誉) 加权投票，票数不足 min_votes 视为“证据不足”（退还质押、不处罚）。

相关需求：REQ-OR-004, REQ-OR-005
"""

from __future__ import annotations

from dataclasses import dataclass, field

KINDS = ("appeal", "report")


@dataclass
class Dispute:
    dispute_id: str
    kind: str
    claimant: str
    target: str
    original: str
    stake: int
    opened_at: int
    jurors: tuple[str, ...] = ()
    votes: dict[str, tuple[bool, float]] = field(default_factory=dict)
    drawn: bool = False
    resolved: bool = False
    outcome: str = ""  # upheld | rejected | insufficient


def tally(d: Dispute, min_votes: int) -> str:
    if len(d.votes) < min_votes:
        return "insufficient"
    yes = sum(w for v, w in d.votes.values() if v)
    no = sum(w for v, w in d.votes.values() if not v)
    return "upheld" if yes > no else "rejected"
