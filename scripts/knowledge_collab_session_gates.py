 # -*- coding: utf-8 -*-
"""PRD-410/T3（trend issue #1970 的 T3 环节）：知识共建会话 闸门。

按 T1 设计 §5 落地，消费 T2 knowledge_collab_session 产物（注入式只读）：
  - mark_baseline + append_only_gate：会话日志只增不删复核（基线锚单调
    不减 + 首条原样），破坏 LEDGER_DRIFT 显形；
  - accept_gate：双向对账——accepted 条目必须有 accept 事件且署名齐全；
    缺署名 SESSION_INCOMPLETE 显形；
  - outlet_gate：出口产物核对——被拦条目混入出口 SESSION_STATE_CONFLICT；
  - gate_summary 多闸一票否决合并显形。
ERROR_CODES 随模块导出（348 教训）；零网络；闸门只读。
测试：test_knowledge_collab_session_gates.py
"""
from __future__ import annotations

from typing import Any

import knowledge_collab_session as _t2  # noqa: F401   # 同族（T1 §0）

GATE_SCHEMA = "knowledge-collab-session/v1-gate/v1"
GATE_CODES = ("LEDGER_DRIFT", "SESSION_INCOMPLETE", "SESSION_STATE_CONFLICT")
ERROR_CODES = GATE_CODES   # 错误码词表（与闸门同源，随模块导出——348 教训）


def _fail(gate: str, reasons: list[str]) -> dict[str, Any]:
    return {"schema": GATE_SCHEMA, "gate": gate, "reasons": reasons}


def mark_baseline(ledger: Any) -> None:
    events = getattr(ledger, "events", None)
    if not callable(events):
        raise ValueError("账本无 events 方法——非 CollabSessionLedger")
    rows = events()
    ledger._gate_baseline_len = len(rows)
    ledger._gate_baseline_first = dict(rows[0]) if rows else None


def append_only_gate(ledger: Any) -> dict[str, Any]:
    events = getattr(ledger, "events", None)
    if not callable(events):
        return _fail("LEDGER_DRIFT",
                     ["账本无 events 方法——非 CollabSessionLedger"])
    rows = events()
    if getattr(ledger, "_gate_baseline_len", None) is not None:
        if len(rows) < ledger._gate_baseline_len:
            return _fail("LEDGER_DRIFT",
                         [f"事件流长度 {len(rows)} < 基线 "
                          f"{ledger._gate_baseline_len}——发生删除"
                          "（LEDGER_DRIFT）"])
    first = getattr(ledger, "_gate_baseline_first", None)
    if first is not None and rows and rows[0] != first:
        return _fail("LEDGER_DRIFT",
                     ["首条事件被改写——append-only 破坏（LEDGER_DRIFT）"])
    return _fail("pass", [])


def accept_gate(ledger: Any) -> dict[str, Any]:
    """双向对账（R4）：accepted 必有 accept 事件且署名齐全。"""
    reasons: list[str] = []
    rows = ledger.events()
    accepted_ids = {e["entry_id"] for e in rows if e["event"] == "accept"}
    state = ledger.statuses()
    for eid, st in state.items():
        if st == "accepted" and eid not in accepted_ids:
            reasons = reasons + [f"{eid} 状态 accepted 但无 accept 事件"
                                 "（SESSION_STATE_CONFLICT）"]
        if st == "accepted" and eid in accepted_ids:
            ev = [e for e in rows if e["event"] == "accept"
                  and e["entry_id"] == eid][-1]
            if not ev.get("author") or not ev.get("at"):
                reasons = reasons + [f"{eid} accept 事件缺署名"
                                     "（SESSION_INCOMPLETE）"]
    if not reasons:
        return _fail("pass", [])
    code = "SESSION_INCOMPLETE" if any("INCOMPLETE" in r for r in reasons) \
        else "SESSION_STATE_CONFLICT"
    return _fail(code, reasons)


def outlet_gate(out: dict[str, Any]) -> dict[str, Any]:
    """出口闸门（R1）：被拦条目混入出口按 entry_id 比对显形。"""
    reasons: list[str] = []
    for e in out.get("accepted") or []:
        if not e.get("entry_id"):
            reasons = reasons + ["出口条目缺标识（SESSION_INCOMPLETE）"]
    accepted_ids = {e.get("entry_id") for e in out.get("accepted") or []}
    for b in out.get("blocked") or []:
        if b.get("entry_id") in accepted_ids:
            reasons = reasons + [f"被拦条目 {b.get('entry_id')} 同时出现在"
                                 "出口 accepted——未接受混入"
                                 "（SESSION_STATE_CONFLICT）"]
    if not reasons:
        return _fail("pass", [])
    code = "SESSION_INCOMPLETE" if any("INCOMPLETE" in r for r in reasons) \
        else "SESSION_STATE_CONFLICT"
    return _fail(code, reasons)


def gate_summary(gates: list[dict[str, Any]]) -> dict[str, Any]:
    reasons = [r for g in gates for r in g.get("reasons", [])]
    return {"schema": GATE_SCHEMA,
            "gate": "pass" if not reasons else "block",
            "gates_checked": len(gates), "reasons": reasons}
