# -*- coding: utf-8 -*-
"""PRD-585/T3（trend issue #2937 的 T3 环节）：巡检校验闸门。

按 T1 设计（docs/plans/2026-11-20-prd-585-mindkit-hunting-design.md）§5 落地：
  - append_only_gate：FINDING 留痕 JSONL 只增不删复核，破坏
    FINDING_LEDGER_DRIFT 显形；
  - check_repro_evidence：复现证据可验证——finding 无「复现」repro 或
    空证据 → REPRO_MISSING 拦下（无复现证据的 finding 不入账）；
  - check_fp_veto：误报复核一票否决——review=「误报」的条目仍在收件
    集合里 → FP_ADMIT 拦下；
  - check_hunt_vocab：巡检结论词表封闭复核；
  - gate_summary：多闸一票否决。
零网络零子进程；示例全虚构占位。
测试：test_mindkit_hunt_gate.py
"""
from __future__ import annotations

from typing import Any

GATE_SCHEMA = "mindkit-hunt-gate/v1"
ERROR_CODES = ("FINDING_LEDGER_DRIFT", "REPRO_MISSING", "FP_ADMIT",
               "HUNT_VOCAB_GAP")
FINDING_REQUIRED = ("finding", "repro", "evidence", "found_at")
HUNT_CONCLUSIONS = ("有发现", "无可复现发现")


def _fail(code: str, detail: str) -> dict[str, Any]:
    return {"schema": GATE_SCHEMA, "gate": "block",
            "reasons": [{"code": code, "detail": detail}]}


def _pass() -> dict[str, Any]:
    return {"schema": GATE_SCHEMA, "gate": "pass", "reasons": []}


def append_only_gate(entries: list[dict[str, Any]],
                     baseline_first: dict[str, Any] | None,
                     baseline_len: int) -> dict[str, Any]:
    """FINDING 留痕只增不删复核。"""
    if len(entries) < baseline_len:
        return _fail("FINDING_LEDGER_DRIFT",
                     f"账目长度 {len(entries)} < 基线 {baseline_len}——发生删除")
    if baseline_first is not None and entries and entries[0] != baseline_first:
        return _fail("FINDING_LEDGER_DRIFT", "首条留痕被改写")
    return _pass()


def check_repro_evidence(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """复现证据可验证：无「复现」repro 或空证据 → REPRO_MISSING。"""
    for e in entries:
        if e.get("repro") != "复现" or not str(e.get("evidence", "")).strip():
            return _fail("REPRO_MISSING",
                         f"finding 无复现证据：{e.get('finding', '')!r}")
    return _pass()


def check_fp_veto(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """误报复核一票否决：review=「误报」的条目仍在集合里 → FP_ADMIT。"""
    fps = [e for e in entries if e.get("review") == "误报"]
    if fps:
        return _fail("FP_ADMIT",
                     f"{len(fps)} 条误报未摘除——复核后先摘除再进收件箱")
    return _pass()


def check_hunt_vocab(hunt: str) -> dict[str, Any]:
    """巡检结论词表封闭。"""
    if hunt not in HUNT_CONCLUSIONS:
        return _fail("HUNT_VOCAB_GAP", f"巡检结论词表外：{hunt!r}")
    return _pass()


def gate_summary(checks: list[dict[str, Any]]) -> dict[str, Any]:
    """多闸一票否决。"""
    reasons = [r for c in checks for r in c.get("reasons", [])]
    return {"schema": GATE_SCHEMA, "gate": "block" if reasons else "pass",
            "gates_checked": len(checks), "reasons": reasons}
