# -*- coding: utf-8 -*-
"""PRD-539/T3（trend issue #2615 的 T3 环节）：mind-kit 知识方法论包 方法论包校验闸门。

按 T1 设计（docs/plans/2026-11-19-prd-539-mindkit-methodology-design.md）§3/§5 落地：
  - check_pack(has_pack)：无方法论包的技能进上游审批 → PACK_MISSING 拦下
    （R1 无方法论包的技能不成套、不进上游审批）；
  - check_pattern_entry(entry)：模式条目四件缺一 → PATTERN_INCOMPLETE
    （R2 模式条目必带证据来源与口径版本）；
  - check_workflow(steps)：跳步/乱步/多步 → STEP_INVALID（R3 步骤封闭可
    验证，绑定 T2 的 check_step_sequence）；
  - gate_summary：多闸一票否决。
零网络零子进程；示例全虚构占位。
测试：tests/test_mindkit_methodology_gate.py
"""
from __future__ import annotations

from typing import Any

from mindkit_methodology import (  # noqa: E402
    PATTERN_REQUIRED, WORKFLOW_STEPS, MethodologyError, PatternLedger,
    check_step_sequence)

GATE_SCHEMA = "mindkit-methodology-gate/v1"
GATE_PRD = 539
GATE_REPO = "mind-kit"
ERROR_CODES = ("PACK_MISSING", "PATTERN_INCOMPLETE", "STEP_INVALID")
BLOCKING_KINDS = ("失效", "过期", "重叠已确认")


class GateError(ValueError):
    """方法论包闸门违规——显形拒绝。"""


def _reason(code: str, target: Any, detail: str) -> dict[str, Any]:
    return {"code": code, "target": target, "detail": detail}


def check_pack(has_pack: Any, skill_id: str = "") -> dict[str, Any]:
    """R1：无方法论包的技能不成套、不进上游审批。"""
    if not has_pack:
        return {"allowed": False,
                "reasons": [_reason("PACK_MISSING", skill_id or "unknown",
                                    "无方法论包——技能不成套，不进上游审批")],
                "gate": "blocked"}
    return {"allowed": True, "reasons": [], "gate": "passed"}


def enforce_pack(has_pack: Any, skill_id: str = "") -> dict[str, Any]:
    d = check_pack(has_pack, skill_id)
    if not d["allowed"]:
        raise GateError(f"GATE_BLOCKED：{d['reasons'][0]['detail']}")
    return d


def check_pattern_entry(entry: Any) -> dict[str, Any]:
    """R2：模式条目四件缺一 → PATTERN_INCOMPLETE。"""
    if not isinstance(entry, dict):
        return {"allowed": False,
                "reasons": [_reason("PATTERN_INCOMPLETE", None,
                                    "条目非对象")],
                "gate": "blocked"}
    missing = [k for k in PATTERN_REQUIRED
               if not isinstance(entry.get(k), str)
               or not entry.get(k).strip()]
    if missing:
        return {"allowed": False,
                "reasons": [_reason("PATTERN_INCOMPLETE",
                                    entry.get("pattern") or "unknown",
                                    f"模式条目缺 {missing}")],
                "gate": "blocked"}
    return {"allowed": True, "reasons": [], "gate": "passed"}


def check_workflow(steps: Any) -> dict[str, Any]:
    """R3：workflow 步骤封闭可验证（绑定 T2 check_step_sequence）。"""
    d = check_step_sequence(steps)
    if not d["ok"]:
        return {"allowed": False,
                "reasons": [_reason("STEP_INVALID", None, d["detail"])],
                "gate": "blocked"}
    return {"allowed": True, "reasons": [], "gate": "passed"}


def gate_summary(checks: list[dict[str, Any]]) -> dict[str, Any]:
    """多闸一票否决。"""
    reasons = [r for c in checks for r in c.get("reasons", [])]
    return {"schema": GATE_SCHEMA, "gate": "pass" if not reasons else "block",
            "gates_checked": len(checks), "reasons": reasons}
