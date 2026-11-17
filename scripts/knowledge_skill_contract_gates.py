# -*- coding: utf-8 -*-
"""PRD-515/T3（trend issue #2497 的 T3 环节）：知识条目技能契约闸门。

按 T1 设计 §6 落地：
  - mark_baseline + append_only_gate：契约校验结果账本只增不删复核，
    破坏 LEDGER_DRIFT 显形；
  - gate_summary 多闸一票否决合并显形。
零 LLM 零网络零子进程；示例全虚构占位。
测试：test_knowledge_skill_contract_gates.py
"""
from __future__ import annotations

from typing import Any

GATE_SCHEMA = "skill-contract-gate/v1"
GATE_CODES = ("LEDGER_DRIFT",)
ERROR_CODES = GATE_CODES


def _fail(gate: str, reasons: list[str]) -> dict[str, Any]:
    return {"schema": GATE_SCHEMA, "gate": gate, "reasons": reasons}


def mark_baseline(ledger: Any) -> None:
    entries = getattr(ledger, "entries", None)
    if not callable(entries):
        raise ValueError("账本无 entries 方法——非 ContractLedger")
    rows = entries()
    ledger._gate_baseline_len = len(rows)
    ledger._gate_baseline_first = dict(rows[0]) if rows else None


def append_only_gate(ledger: Any) -> dict[str, Any]:
    entries = getattr(ledger, "entries", None)
    if not callable(entries):
        return _fail("LEDGER_DRIFT", ["账本无 entries 方法"])
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


def gate_summary(gates: list[dict[str, Any]]) -> dict[str, Any]:
    reasons = [r for g in gates for r in g.get("reasons", [])]
    return {"schema": GATE_SCHEMA,
            "gate": "pass" if not reasons else "block",
            "gates_checked": len(gates), "reasons": reasons}
