"""AIO-010~013/030~034 成果评审网关。

编排循环此前只数「任务状态是不是 completed」——执行者交一句「做完了」
和交一份合格产出，在循环里没有区别。本模块补的就是这一段。

**第一性约束：模型永远不能单独动钱。**
评审结果只用于「谁该看一眼」的分诊：
  pass   → 建议通过，放款仍由发布方确认（或既有的超时自动验收）
  revise → 生成整改要点通知执行者，**不改变任何资金状态**
  fail   → 进人工复核，**不自动扣款、不自动罚没**
模型会错，而资金操作不可逆。
"""
import json
import time
from dataclasses import dataclass, field
from typing import Protocol

from sqlalchemy.orm import Session

from app.core.observability import redact

PROMPT_VERSION = "review-v1"
# AIO-020 质量闸门：已完成步的平均分低于此线不算达标
QUALITY_BAR = 60


@dataclass
class ReviewResult:
    verdict: str = "pass"        # pass / revise / fail
    score: int = 100
    reasons: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    reviewer: str = "rule"


class ReviewGateway(Protocol):
    name: str

    def review(self, criteria: list, evidence: dict) -> ReviewResult: ...


# ── 证据采集（两种实现共用同一份输入）────────────────────────────
def collect_evidence(db: Session, task_id: int) -> dict:
    """把一个任务的可观测事实汇总成评审输入。

    只取**结构化事实**，不取聊天记录——聊天里全是手机号、地址一类的
    个人信息，送进模型既不必要也不合规（AIO-033）。
    """
    from app.modules.task.models import ProgressLog, Task

    task = db.get(Task, task_id)
    if not task:
        return {}
    logs = db.query(ProgressLog).filter(ProgressLog.task_id == task_id).all()
    images = [u for log in logs for u in (log.images or [])]
    delivery = [log for log in logs if log.kind == "delivery"]
    return {
        "task_id": task.id,
        "title": task.title,
        "status": task.status,
        "reject_count": task.reject_count,
        "progress_notes": [redact(log.content)[:300] for log in logs if log.content][:20],
        "progress_count": len(logs),
        "checkin_count": sum(1 for log in logs if log.kind == "checkin"),
        "image_count": len(images),
        "delivery_note": redact(delivery[-1].content)[:500] if delivery else "",
        "auto_accepted": task.status == "completed" and not delivery,
    }


class RuleReview:
    """缺省实现：**基于可观测事实真打分**，不是假装通过。

    这不是占位符——即便永远不接模型，这套规则也能把「零留痕、零凭证、
    多次驳回」的交付和「有打卡、有照片、一次通过」的交付区分开。
    """

    name = "rule"

    def review(self, criteria: list, evidence: dict) -> ReviewResult:
        if not evidence:
            return ReviewResult("fail", 0, ["没有可评审的任务数据"], ["交付记录"], self.name)

        score = 60  # 基准：任务被验收通过即及格
        reasons: list[str] = []
        missing: list[str] = []

        if evidence.get("progress_count", 0) >= 2:
            score += 10
            reasons.append("有多条执行留痕")
        else:
            missing.append("执行过程留痕（至少 2 条进度说明）")

        if evidence.get("image_count", 0) > 0:
            score += 15
            reasons.append(f"附了 {evidence['image_count']} 张图片凭证")
        else:
            missing.append("图片凭证（纠纷时最有力的证据）")

        if evidence.get("checkin_count", 0) > 0:
            score += 5
            reasons.append("有到场打卡")

        if evidence.get("delivery_note"):
            score += 10
            reasons.append("有交付说明")
        else:
            missing.append("交付说明")

        # 驳回过说明一次没做对，但最终通过了 → 扣分不否定
        rejects = evidence.get("reject_count", 0)
        if rejects:
            score -= min(20, rejects * 10)
            reasons.append(f"经历 {rejects} 次驳回返工")

        score = max(0, min(100, score))
        verdict = "pass" if score >= QUALITY_BAR else "revise"
        return ReviewResult(verdict, score, reasons, missing, self.name)


# ── AIO-011 模型评审的结构化输出契约 ──────────────────────────────
REVIEW_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "verdict": {"type": "string", "enum": ["pass", "revise", "fail"]},
        "score": {"type": "integer"},
        "reasons": {"type": "array", "items": {"type": "string"}},
        "missing": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["verdict", "score", "reasons", "missing"],
}

REVIEW_SYSTEM = (
    "你是任务协作平台的成果评审员。依据给定的验收要点，判断执行者的交付是否达标。"
    "只依据提供的事实判断，事实不足时给 revise 并在 missing 中写清还缺什么，"
    "不要臆测。score 为 0-100 的达标程度。只返回结构化数据。"
)


class ModelReview:
    """模型评审：结构化输出 + 服务端校验，任何异常降级 RuleReview。"""

    def __init__(self, model: str = "claude-opus-4-8"):
        self.model = model
        self.name = f"anthropic:{model}"
        self._fallback = RuleReview()

    def _call(self, criteria: list, evidence: dict) -> ReviewResult:
        from anthropic import Anthropic

        client = Anthropic()
        prompt = (
            f"验收要点：{json.dumps(criteria, ensure_ascii=False)}\n"
            f"交付事实：{json.dumps(evidence, ensure_ascii=False)}\n"
            "请给出评审结论。"
        )
        message = client.messages.create(
            model=self.model,
            max_tokens=2048,
            system=REVIEW_SYSTEM,
            thinking={"type": "adaptive"},
            output_config={"format": {"type": "json_schema", "schema": REVIEW_SCHEMA}},
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in message.content if getattr(b, "type", "") == "text")
        raw = json.loads(text)
        verdict = raw["verdict"]
        if verdict not in ("pass", "revise", "fail"):
            raise ValueError("verdict 不合规")
        score = int(raw["score"])
        if not 0 <= score <= 100:
            raise ValueError("score 越界")
        return ReviewResult(verdict, score, list(raw.get("reasons", [])),
                            list(raw.get("missing", [])), self.name)

    def review(self, criteria: list, evidence: dict) -> ReviewResult:
        try:
            return self._call(criteria, evidence)
        except Exception:
            # AIO-040/042 降级：无 Key / 超时 / 输出不合规都回落规则评审
            return self._fallback.review(criteria, evidence)


_gateway: ReviewGateway | None = None


def get_review_gateway() -> ReviewGateway:
    global _gateway
    if _gateway is None:
        import os

        _gateway = (
            ModelReview(os.environ.get("PLATFORM_LLM_MODEL", "claude-opus-4-8"))
            if os.environ.get("ANTHROPIC_API_KEY")
            else RuleReview()
        )
    return _gateway


def set_review_gateway(gateway: ReviewGateway | None) -> None:
    """测试/生产替换实现。"""
    global _gateway
    _gateway = gateway


def run_review(db: Session, mission, step) -> ReviewResult:
    """执行一次评审并落留痕。

    模型调用配额（AIO-034）在这里把关：达上限即降级规则评审，
    不静默烧 API 账单。
    """
    from app.core.config import settings

    from .models import StepReview

    gateway = get_review_gateway()
    is_model = gateway.name != "rule"
    if is_model and mission.model_calls >= settings.ORC_MAX_MODEL_CALLS:
        gateway = RuleReview()
        is_model = False

    evidence = collect_evidence(db, step.task_id) if step.task_id else {}
    criteria = list(step.acceptance or []) or list(mission.acceptance_criteria or [])

    started = time.time()
    result = gateway.review(criteria, evidence)
    duration = int((time.time() - started) * 1000)

    if is_model:
        mission.model_calls += 1
        db.add(mission)

    db.add(StepReview(
        step_id=step.id, reviewer=result.reviewer, prompt_version=PROMPT_VERSION,
        verdict=result.verdict, score=result.score,
        reasons=result.reasons, missing=result.missing,
        # AIO-033 只落脱敏摘要：原始证据里可能有地址一类的个人信息
        input_digest=redact(json.dumps(
            {k: v for k, v in evidence.items() if k != "progress_notes"},
            ensure_ascii=False))[:400],
        duration_ms=duration,
    ))
    step.review_verdict = result.verdict
    step.review_score = result.score
    step.review_missing = result.missing
    db.add(step)
    return result
