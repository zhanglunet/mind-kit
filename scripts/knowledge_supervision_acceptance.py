# -*- coding: utf-8 -*-
"""PRD-456/T5（trend issue #2204 的 T5 环节）：知识监督台验收试运行。

按 T1 设计（docs/plans/2026-11-15-prd-456-knowledge-supervision-bench-design.md）
§7 验收标准，把 T2 最小实现（knowledge_supervision_bench.py）、T3 闸门
（knowledge_supervision_gate.py）、T4 划界断言（tests/test_prd456_t4_
supervision_boundary.py 的断言口径）串起来全链跑一遍端到端验证，不改
前几步的设计与代码，只新增本验收脚本：

  - 全链：来源不明的知识整理时被批注发回换来源 → agent 改完回来
    （版本 +1、旧批注带到新版上对照）→ 人点头 → 过闸 → 只留点头过的
    知识进下游；三件套（进度/批注/发回反馈）全程落账可查；
  - 反例：待审/已发回/无记录的知识一律拦在下游之外，无记录的还记一条
    出口绕过告警；一批里有一条被拦即整批 vetoed；
  - 旧点头不放行新版：v2 的点头对 v3 失效，改完回来须重新点头；
  - 有未处理批注却点头即拒绝；发回与点头不能同一次。

运行：python3 scripts/knowledge_supervision_acceptance.py（仓库根执行；
只跑内存里的合成占位数据，零网络零子进程，退出码 0 即全链跑通）。
测试：tests/test_prd456_t5_knowledge_supervision_acceptance.py
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from knowledge_supervision_bench import (  # noqa: E402
    SupervisionError, SupervisionLedger, revise, supervise,
)
from knowledge_supervision_gate import SupervisionGate  # noqa: E402

SCHEMA = "knowledge-supervision-acceptance/v1"
NOW = "2026-11-16T09:00:00Z"
LATER = "2026-11-16T10:00:00Z"
ITEM_V1 = {"knowledge_id": "k-001", "version": 1,
           "sources": ["来源 A（占位）"], "tags": ["标签甲（占位）"]}
ITEM_V2 = {"knowledge_id": "k-001", "version": 2,
           "sources": ["来源 B（占位）"], "tags": ["标签甲（占位）"]}
ANNOTATION = {"annotation_id": "a-001", "anchor": "来源 A（占位）",
              "type": "换来源", "text": "来源 A 查无出处，请换来源（占位）",
              "author": "reviewer-placeholder", "at": NOW, "status": "待处理"}
ANNOTATION_RESOLVED = dict(ANNOTATION, status="已采纳")


def _scenario(name: str, passed: bool, detail: str) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "detail": detail}


def happy_path() -> tuple[dict[str, Any], dict[str, Any]]:
    """全链主场景：批注发回 → 改回 v2 → 点头 → 过闸 → 入账。

    返回（最终 approved 记录，场景小结）。
    """
    ledger = SupervisionLedger()
    pending = supervise(copy.deepcopy(ITEM_V1), [copy.deepcopy(ANNOTATION)],
                        at=NOW)
    assert pending["verdict"] == "pending"
    returned = supervise(copy.deepcopy(ITEM_V1), [copy.deepcopy(ANNOTATION)],
                         {"kind": "换来源", "text": "请换一个来源（占位）"},
                         at=NOW)
    assert returned["verdict"] == "returned"
    assert len(returned["feedback_rounds"]) == 1
    revised = revise(returned, copy.deepcopy(ITEM_V2), at=LATER)
    assert revised["verdict"] == "pending" and revised["version"] == 2
    assert revised["annotations"] == returned["annotations"]
    assert revised["feedback_rounds"][-1]["revised_knowledge_id"] == "k-001"
    approved = supervise(copy.deepcopy(ITEM_V2),
                         [copy.deepcopy(ANNOTATION_RESOLVED)],
                         approve=True, at=LATER)
    assert approved["verdict"] == "approved"
    for rec in (pending, returned, revised, approved):
        ledger.record(rec)
    gate = SupervisionGate(ledger)
    verdict = gate.gate(copy.deepcopy(ITEM_V2), at=LATER)
    assert verdict["decision"] == "pass"
    other_pending = {"knowledge_id": "k-002", "version": 1,
                     "sources": ["来源占位"], "tags": ["标签占位"]}
    ledger.record(supervise(copy.deepcopy(other_pending), at=NOW))
    no_record = {"knowledge_id": "k-003", "version": 1,
                 "sources": ["来源占位"], "tags": ["标签占位"]}
    batch = gate.gate_outlet([copy.deepcopy(ITEM_V2),
                              copy.deepcopy(other_pending),
                              copy.deepcopy(no_record)], at=LATER)
    assert [p["knowledge_id"] for p in batch["passed"]] == ["k-001"]
    assert batch["blocked_count"] == 2 and batch["vetoed"] is True
    assert len(batch["bypass_alerts"]) == 1
    outlet = ledger.outlet([copy.deepcopy(ITEM_V2),
                            copy.deepcopy(other_pending)])
    assert [p["knowledge_id"] for p in outlet["passed"]] == ["k-001"]
    steps = [s["step"] for rec in (pending, returned, revised, approved)
             for s in rec["progress"]]
    assert sorted(set(steps)) == ["approved", "drafted", "returned", "revised"]
    latest = ledger.latest_for("k-001")
    assert latest is not None and latest["verdict"] == "approved"
    assert latest["version"] == 2
    return approved, _scenario(
        "happy-path-full-chain", True,
        "k-001：整理→批注（换来源）→发回→改回v2（来源 A→B）→点头→过闸→入账；"
        "进度 drafted/returned/revised/approved 四步齐全，旧批注带到新版；"
        "出口只放行已点头的 k-001 v2，k-002 待审与无记录的 k-003 被拦、整批 vetoed")


def unapproved_blocked() -> dict[str, Any]:
    """反例：待审/已发回/无记录一律拦在下游之外，无记录的记绕过告警。"""
    ledger = SupervisionLedger()
    pending = supervise(copy.deepcopy(ITEM_V1), [copy.deepcopy(ANNOTATION)],
                        at=NOW)
    ledger.record(pending)
    returned = supervise(copy.deepcopy(ITEM_V1), [copy.deepcopy(ANNOTATION)],
                         {"kind": "换来源", "text": "请换来源（占位）"},
                         at=NOW)
    ledger.record(returned)
    gate = SupervisionGate(ledger)
    v_pending = gate.gate(copy.deepcopy(ITEM_V1), at=NOW)
    assert v_pending["decision"] == "block"
    assert v_pending["reason"] == "NOT_APPROVED"
    no_record = {"knowledge_id": "k-009", "version": 1,
                 "sources": ["来源占位"], "tags": ["标签占位"]}
    v_bypass = gate.gate(copy.deepcopy(no_record), at=NOW)
    assert v_bypass["decision"] == "block"
    assert v_bypass["reason"] == "SUPERVISION_OUTLET_BYPASS"
    assert len(gate.alerts()) == 1
    batch = gate.gate_outlet([copy.deepcopy(ITEM_V1),
                              copy.deepcopy(no_record)], at=NOW)
    assert batch["vetoed"] is True and batch["blocked_count"] == 2
    return _scenario(
        "unapproved-blocked", True,
        "待审 k-001 拦下（NOT_APPROVED）；无记录的 k-009 拦下并记一条"
        " SUPERVISION_OUTLET_BYPASS 告警；一批有拦即整批 vetoed")


def old_approval_does_not_admit_new_version() -> dict[str, Any]:
    """旧点头不放行新版：v2 的点头对 v3 失效，改完回来须重新点头。"""
    approved, _ = happy_path()
    ledger = SupervisionLedger()
    ledger.record(approved)
    gate = SupervisionGate(ledger)
    assert gate.gate(copy.deepcopy(ITEM_V2), at=LATER)["decision"] == "pass"
    v3 = dict(ITEM_V2, version=3)
    out = gate.gate(copy.deepcopy(v3), at=LATER)
    assert out["decision"] == "block"
    assert out["reason"] == "VERSION_MISMATCH"
    return _scenario(
        "old-approval-does-not-admit-new-version", True,
        "v2 已点头放行；v3 以 VERSION_MISMATCH 拦下，须重新点头")


def approve_with_unresolved_refused() -> dict[str, Any]:
    """有未处理批注却点头即拒绝；发回与点头不能同一次。"""
    refused = supervise(copy.deepcopy(ITEM_V1),
                        [copy.deepcopy(ANNOTATION)], approve=True, at=NOW)
    assert refused.get("refused") == "SUPERVISION_VERDICT_MISMATCH"
    both = supervise(copy.deepcopy(ITEM_V1), [copy.deepcopy(ANNOTATION)],
                     {"kind": "换来源", "text": "请换来源（占位）"},
                     approve=True, at=NOW)
    assert both.get("refused") == "SUPERVISION_VERDICT_MISMATCH"
    ledger = SupervisionLedger()
    try:
        ledger.record(refused)
    except SupervisionError:
        pass
    else:  # pragma: no cover - 被拒绝的记录入账即验收失败
        raise AssertionError("被拒绝的监督记录进了账本")
    return _scenario(
        "approve-with-unresolved-refused", True,
        "有未处理批注却点头 → SUPERVISION_VERDICT_MISMATCH 拒绝；发回与点头"
        "同一次 → 同样拒绝；被拒绝的记录拒绝入账")


def three_records_complete() -> dict[str, Any]:
    """三件套落账：进度/批注/发回反馈缺一不可，账本缺件拒绝入账。"""
    approved, _ = happy_path()
    ledger = SupervisionLedger()
    pending = supervise(copy.deepcopy(ITEM_V1), [copy.deepcopy(ANNOTATION)],
                        at=NOW)
    returned = supervise(copy.deepcopy(ITEM_V1), [copy.deepcopy(ANNOTATION)],
                         {"kind": "换来源", "text": "请换来源（占位）"},
                         at=NOW)
    revised = revise(returned, copy.deepcopy(ITEM_V2), at=LATER)
    for rec in (pending, returned, revised, approved):
        ledger.record(rec)
    assert len(ledger.entries()) == 4
    assert all(rec["progress"] for rec in ledger.entries())
    assert any(rec["annotations"] for rec in ledger.entries())
    assert any(rec["feedback_rounds"] for rec in ledger.entries())
    assert ledger.latest_for("k-001")["verdict"] == "approved"
    broken = copy.deepcopy(approved)
    broken["feedback_rounds"] = []
    broken["verdict"] = "returned"
    try:
        ledger.record(broken)
    except SupervisionError:
        pass
    else:  # pragma: no cover - verdict 与发回轮次对不上的记录入账即验收失败
        raise AssertionError("verdict=returned 却无发回轮次的记录进了账本")
    return _scenario(
        "three-records-complete", True,
        "链上 4 条记录：进度/批注/发回反馈齐全；账本 4 条、最新一条为 approved"
        " v2；verdict=returned 却无发回轮次的记录拒绝入账")


def run_acceptance() -> dict[str, Any]:
    """跑完全部验收场景，返回验收报告（全过 verdict 为“全链跑通”）。"""
    scenarios = [
        happy_path()[1],
        unapproved_blocked(),
        old_approval_does_not_admit_new_version(),
        approve_with_unresolved_refused(),
        three_records_complete(),
    ]
    passed = sum(1 for s in scenarios if s["passed"])
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "verdict": "全链跑通" if passed == len(scenarios) else "验收失败",
        "scenarios": scenarios,
        "passed_count": passed,
        "total_count": len(scenarios),
    }
    return report


def main() -> int:
    report = run_acceptance()
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["verdict"] == "全链跑通" else 1


if __name__ == "__main__":
    raise SystemExit(main())
