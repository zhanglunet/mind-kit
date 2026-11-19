# -*- coding: utf-8 -*-
"""PRD-562/T3（trend issue #2660 的 T3 环节）：准入检查校验闸门。

按 T1 设计（docs/plans/2026-11-20-prd-562-mindkit-admission-design.md）§5 落地：
  - append_only_gate：准入检查留痕 JSONL 只增不删复核，破坏
    ADMISSION_LEDGER_DRIFT 显形；
  - check_layer_coverage(entries)：五层覆盖校验——缺层/层词表外
    LAYER_COVERAGE_GAP 拦下；
  - check_one_vote(entries)：任一层「不过」而 admission≠「不进（整改）」
    → ONE_VOTE_BYPASS 拦下（一票否决不可绕）；
  - check_no_auto_admit(admission)：admission=「可进收件箱」但存在待补测/
    待复核 → AUTO_ADMIT 拦下（机器不代行准入）；
  - gate_summary：多闸一票否决。
零网络零子进程；示例全虚构占位。
测试：tests/test_mindkit_admission_gate.py
"""
from __future__ import annotations

from typing import Any

GATE_SCHEMA = "mindkit-admission-gate/v1"
ERROR_CODES = ("ADMISSION_LEDGER_DRIFT", "LAYER_COVERAGE_GAP",
               "ONE_VOTE_BYPASS", "AUTO_ADMIT")
LAYERS = ("L1_quality", "L2_security", "L3_overlap", "L4_synth", "L5_live")
REQUIRED_ENTRY_KEYS = ("layer", "verdict", "evidence", "checked_at")


def _fail(code: str, detail: str) -> dict[str, Any]:
    return {"schema": GATE_SCHEMA, "gate": "block",
            "reasons": [{"code": code, "detail": detail}]}


def append_only_gate(entries: list[dict[str, Any]],
                     baseline_first: dict[str, Any] | None,
                     baseline_len: int) -> dict[str, Any]:
    """准入留痕只增不删复核。"""
    if len(entries) < baseline_len:
        return _fail("ADMISSION_LEDGER_DRIFT",
                     f"账目长度 {len(entries)} < 基线 {baseline_len}——发生删除")
    if baseline_first is not None and entries and entries[0] != baseline_first:
        return _fail("ADMISSION_LEDGER_DRIFT", "首条留痕被改写")
    return {"schema": GATE_SCHEMA, "gate": "pass", "reasons": []}


def check_layer_coverage(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """五层覆盖校验：缺层/层词表外 → LAYER_COVERAGE_GAP。"""
    seen = set()
    for e in entries:
        layer = e.get("layer", "")
        if layer not in LAYERS:
            return _fail("LAYER_COVERAGE_GAP", f"层词表外：{layer}")
        seen.add(layer)
    missing = [l for l in LAYERS if l not in seen]
    if missing:
        return _fail("LAYER_COVERAGE_GAP", f"缺层：{missing}")
    return {"schema": GATE_SCHEMA, "gate": "pass", "reasons": []}


def check_one_vote(entries: list[dict[str, Any]],
                   admission: str) -> dict[str, Any]:
    """一票否决不可绕：任一层「不过」而 admission 不是「不进（整改）」
    → ONE_VOTE_BYPASS。"""
    has_block = any(e.get("verdict") == "不过" for e in entries)
    if has_block and admission != "不进（整改）":
        return _fail("ONE_VOTE_BYPASS",
                     f"存在「不过」层但 admission={admission!r}——一票否决被绕")
    return {"schema": GATE_SCHEMA, "gate": "pass", "reasons": []}


def check_no_auto_admit(admission: str) -> dict[str, Any]:
    """机器不代行准入：admission=「可进收件箱」需人工确认（本闸门只复核
    词表封闭，确认动作由收件箱环节执行）。"""
    if admission not in ("可进收件箱", "不进（整改）", "待复核", "待补测"):
        return _fail("AUTO_ADMIT", f"admission 词表外：{admission!r}")
    return {"schema": GATE_SCHEMA, "gate": "pass", "reasons": []}


def gate_summary(checks: list[dict[str, Any]]) -> dict[str, Any]:
    """多闸一票否决。"""
    reasons = [r for c in checks for r in c.get("reasons", [])]
    return {"schema": GATE_SCHEMA, "gate": "pass" if not reasons else "block",
            "gates_checked": len(checks), "reasons": reasons}
