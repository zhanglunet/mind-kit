# -*- coding: utf-8 -*-
"""PRD-433/T3（trend issue #2085 的 T3 环节）：知识条目评审流水线 闸门。

按 T1 设计 §5 落地，消费 T2 knowledge_review_pipeline 产物（注入式只读）：
  - mark_baseline + append_only_gate：评审账本只增不删复核，破坏
    LEDGER_DRIFT 显形；
  - verdict_gate：结论与判定双向对账（有 confirmed 却 pass / 或反之，
    REVIEW_VERDICT_MISMATCH）；三件套缺件/词表外 REVIEW_INCOMPLETE；
  - coverage_gate：账目判定数与候选数不一致（漏判）REVIEW_INCOMPLETE；
  - gate_summary 多闸一票否决合并显形。
ERROR_CODES 随模块导出（348 教训）；零网络；闸门只读。
测试：tests/test_knowledge_review_pipeline_gates.py
"""
from __future__ import annotations

from typing import Any

   # 同族（T1 §0）

GATE_SCHEMA = "knowledge-review-pipeline/v1-gate/v1"
GATE_CODES = ("LEDGER_DRIFT", "REVIEW_INCOMPLETE", "REVIEW_VERDICT_MISMATCH")
ERROR_CODES = GATE_CODES   # 错误码词表（与闸门同源，随模块导出——348 教训）


def _fail(gate: str, reasons: list[str]) -> dict[str, Any]:
    return {"schema": GATE_SCHEMA, "gate": gate, "reasons": reasons}


def mark_baseline(ledger: Any) -> None:
    entries = getattr(ledger, "entries", None)
    if not callable(entries):
        raise ValueError("账本无 entries 方法——非 ReviewPipelineLedger")
    rows = entries()
    ledger._gate_baseline_len = len(rows)
    ledger._gate_baseline_first = dict(rows[0]) if rows else None


def append_only_gate(ledger: Any) -> dict[str, Any]:
    entries = getattr(ledger, "entries", None)
    if not callable(entries):
        return _fail("LEDGER_DRIFT",
                     ["账本无 entries 方法——非 ReviewPipelineLedger"])
    rows = entries()
    if getattr(ledger, "_gate_baseline_len", None) is not None:
        if len(rows) < ledger._gate_baseline_len:
            return _fail("LEDGER_DRIFT",
                         [f"账目长度 {len(rows)} < 基线 "
                          f"{ledger._gate_baseline_len}——发生删除"
                          "（LEDGER_DRIFT）"])
    first = getattr(ledger, "_gate_baseline_first", None)
    if first is not None and rows and rows[0] != first:
        return _fail("LEDGER_DRIFT",
                     ["首条账目被改写——append-only 破坏（LEDGER_DRIFT）"])
    return _fail("pass", [])


def verdict_gate(record: dict[str, Any]) -> dict[str, Any]:
    """双向对账（R4）：blocked⇔存在 confirmed；三件套缺件显形。"""
    reasons: list[str] = []
    missing = [k for k in ("review_id", "draft_id", "candidates",
                           "judgments", "verdict")
               if record.get(k) in (None, "")]
    if missing:
        reasons = reasons + [f"账目缺 {missing}（REVIEW_INCOMPLETE）"]
    verdict = record.get("verdict")
    if verdict is not None and verdict not in ("pass", "blocked"):
        reasons = reasons + [f"verdict {verdict!r} 词表外（REVIEW_INCOMPLETE）"]
    judgments = record.get("judgments") or []
    confirmed = [j for j in judgments if j.get("verdict") == "confirmed"]
    if verdict == "blocked" and not confirmed:
        reasons = reasons + ["blocked 但无 confirmed 判定"
                             "（REVIEW_VERDICT_MISMATCH）"]
    if verdict == "pass" and confirmed:
        reasons = reasons + ["pass 但存在 confirmed 判定"
                             "（REVIEW_VERDICT_MISMATCH）"]
    if not reasons:
        return _fail("pass", [])
    code = ("REVIEW_INCOMPLETE" if any("INCOMPLETE" in r for r in reasons)
            else "REVIEW_VERDICT_MISMATCH")
    return _fail(code, reasons)


def coverage_gate(record: dict[str, Any]) -> dict[str, Any]:
    """全判齐（R4）：判定数=候选数且逐条对得上。"""
    cands = record.get("candidates") or []
    judgments = record.get("judgments") or []
    ck = sorted((str(c.get("rule_id")), c.get("line")) for c in cands)
    jk = sorted((str(j.get("rule_id")), j.get("line")) for j in judgments)
    if ck != jk:
        return _fail("REVIEW_INCOMPLETE",
                     ["候选与判定不一一对应——存在漏判/多判"
                      "（REVIEW_INCOMPLETE）"])
    return _fail("pass", [])


def gate_summary(gates: list[dict[str, Any]]) -> dict[str, Any]:
    reasons = [r for g in gates for r in g.get("reasons", [])]
    return {"schema": GATE_SCHEMA,
            "gate": "pass" if not reasons else "block",
            "gates_checked": len(gates), "reasons": reasons}
