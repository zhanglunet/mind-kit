# -*- coding: utf-8 -*-
"""PRD-456/T3 测试（trend #2202 的 T3 环节）：知识监督台监督回路闸门。
运行：python -m pytest tests/test_knowledge_supervision_gate.py -q（仓库根执行）
覆盖（T1 §5/§10）：出口拦截 SUPERVISION_OUTLET_BYPASS（无记录拦截并告警）/
verdict 双向对账 SUPERVISION_VERDICT_MISMATCH/一票否决（任一拦下即整批
vetoed）/账本漂移 LEDGER_DRIFT/旧点头不放行新版 VERSION_MISMATCH/
无默认通过（缺件/超时未裁决拦下）/闸门审计 JSONL 落账/词表封闭/AST 零网络。
零网络；全合成占位。
"""
import ast
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from knowledge_supervision_bench import (  # noqa: E402
    SupervisionLedger, supervise,
)
from knowledge_supervision_gate import (  # noqa: E402
    DECISIONS, GATE_CODES, GATE_REASONS, GATE_SCHEMA, SupervisionGate,
)

NOW = "2026-11-15T09:00:00Z"
LATER = "2026-11-15T10:00:00Z"
ITEM = {"knowledge_id": "k-001", "version": 1,
        "sources": ["来源 A（占位）"], "tags": ["标签甲（占位）"]}
FILLER = {"knowledge_id": "k-000", "version": 1,
          "sources": ["来源占位"], "tags": ["标签占位"]}


def _ledger_with(*records):
    led = SupervisionLedger(None)
    for rec in records:
        led.record(rec)
    return led


def _approved_ledger():
    """首条为填充记录（防篡改测试误触漂移），次条为 k-001 已点头记录。"""
    led = _ledger_with(supervise(FILLER, approve=True, at=NOW))
    led.record(supervise(ITEM, approve=True, at=NOW))
    return led


class TestGatePass(unittest.TestCase):
    def test_approved_passes(self):
        gate = SupervisionGate(_approved_ledger())
        out = gate.gate(ITEM, at=NOW)
        self.assertEqual(out["decision"], "pass")
        self.assertIsNone(out["reason"])
        self.assertEqual(out["knowledge_id"], "k-001")

    def test_gate_outlet_all_pass_not_vetoed(self):
        gate = SupervisionGate(_approved_ledger())
        out = gate.gate_outlet([ITEM, FILLER], at=NOW)
        self.assertEqual([d["knowledge_id"] for d in out["passed"]],
                         ["k-001", "k-000"])
        self.assertEqual(out["blocked_count"], 0)
        self.assertFalse(out["vetoed"])
        self.assertEqual(out["bypass_alerts"], [])


class TestOutletBypass(unittest.TestCase):
    def test_no_record_blocked_and_alerted(self):
        gate = SupervisionGate(_approved_ledger())
        unknown = dict(ITEM, knowledge_id="k-999")
        out = gate.gate(unknown, at=NOW)
        self.assertEqual(out["decision"], "block")
        self.assertEqual(out["reason"], "SUPERVISION_OUTLET_BYPASS")
        self.assertEqual(len(gate.alerts()), 1)
        self.assertEqual(gate.alerts()[0]["knowledge_id"], "k-999")

    def test_bypass_vetoes_batch(self):
        gate = SupervisionGate(_approved_ledger())
        unknown = dict(ITEM, knowledge_id="k-999")
        out = gate.gate_outlet([ITEM, unknown], at=NOW)
        self.assertEqual([d["knowledge_id"] for d in out["passed"]],
                         ["k-001"])
        self.assertEqual(out["blocked_count"], 1)
        self.assertEqual(out["blocked"][0]["gate_reason"],
                         "SUPERVISION_OUTLET_BYPASS")
        self.assertTrue(out["vetoed"])
        self.assertEqual(len(out["bypass_alerts"]), 1)


class TestNotApproved(unittest.TestCase):
    def test_pending_blocked(self):
        led = _ledger_with(supervise(FILLER, approve=True, at=NOW))
        led.record(supervise(ITEM, at=NOW))
        gate = SupervisionGate(led)
        out = gate.gate(ITEM, at=NOW)
        self.assertEqual(out["reason"], "NOT_APPROVED")

    def test_returned_blocked(self):
        led = _ledger_with(supervise(FILLER, approve=True, at=NOW))
        ann = [{"text": "换来源（占位）", "type": "换来源"}]
        led.record(supervise(ITEM, ann,
                             {"kind": "换来源", "text": "换来源（占位）"},
                             at=NOW))
        gate = SupervisionGate(led)
        out = gate.gate(ITEM, at=NOW)
        self.assertEqual(out["reason"], "NOT_APPROVED")


class TestVerdictMismatch(unittest.TestCase):
    def test_approved_with_unresolved_annotations(self):
        led = _approved_ledger()
        rec = led._records[1]
        rec["annotations"].append(
            {"annotation_id": "a-999", "anchor": "", "text": "后补批注（占位）",
             "type": "疑问", "author": "reviewer-placeholder", "at": LATER,
             "status": "待处理"})
        gate = SupervisionGate(led)
        out = gate.gate(ITEM, at=NOW)
        self.assertEqual(out["reason"], "SUPERVISION_VERDICT_MISMATCH")

    def test_approved_without_approved_progress(self):
        led = _approved_ledger()
        rec = led._records[1]
        rec["progress"] = [s for s in rec["progress"]
                           if s["step"] != "approved"]
        gate = SupervisionGate(led)
        out = gate.gate(ITEM, at=NOW)
        self.assertEqual(out["reason"], "SUPERVISION_VERDICT_MISMATCH")

    def test_approved_step_without_timestamp(self):
        led = _approved_ledger()
        rec = led._records[1]
        for s in rec["progress"]:
            if s["step"] == "approved":
                s["at"] = ""
        gate = SupervisionGate(led)
        out = gate.gate(ITEM, at=NOW)
        self.assertEqual(out["reason"], "SUPERVISION_VERDICT_MISMATCH")


class TestVersionMismatch(unittest.TestCase):
    def test_old_approval_does_not_pass_new_version(self):
        gate = SupervisionGate(_approved_ledger())
        out = gate.gate(dict(ITEM, version=2), at=NOW)
        self.assertEqual(out["reason"], "VERSION_MISMATCH")

    def test_revised_then_reapproved_passes(self):
        from knowledge_supervision_bench import revise  # noqa: E402
        led = _ledger_with(supervise(FILLER, approve=True, at=NOW))
        ann = [{"text": "换来源（占位）", "type": "换来源"}]
        base = supervise(ITEM, ann,
                         {"kind": "换来源", "text": "换来源（占位）"},
                         at=NOW)
        led.record(base)
        back = revise(base, dict(ITEM, version=2), at=NOW)
        resolved = [dict(a, status="已采纳") for a in back["annotations"]]
        led.record(supervise(dict(ITEM, version=2), resolved,
                             approve=True, at=LATER))
        gate = SupervisionGate(led)
        self.assertEqual(gate.gate(dict(ITEM, version=2), at=LATER)
                         ["decision"], "pass")
        self.assertEqual(gate.gate(dict(ITEM, version=1), at=LATER)
                         ["reason"], "VERSION_MISMATCH")


class TestLedgerDrift(unittest.TestCase):
    def test_first_entry_deleted(self):
        led = _approved_ledger()
        gate = SupervisionGate(led)
        led._records.pop(0)
        out = gate.gate(ITEM, at=NOW)
        self.assertEqual(out["reason"], "LEDGER_DRIFT")

    def test_first_entry_modified(self):
        led = _approved_ledger()
        gate = SupervisionGate(led)
        led._records[0]["version"] = 99
        out = gate.gate_outlet([ITEM], at=NOW)
        self.assertEqual(out["blocked_count"], 1)
        self.assertEqual(out["blocked"][0]["gate_reason"], "LEDGER_DRIFT")
        self.assertTrue(out["vetoed"])


class TestNoDefaultPass(unittest.TestCase):
    def test_missing_id_refused(self):
        gate = SupervisionGate(_approved_ledger())
        out = gate.gate({}, at=NOW)
        self.assertEqual(out["reason"], "SUPERVISION_INCOMPLETE")

    def test_non_dict_refused(self):
        gate = SupervisionGate(_approved_ledger())
        out = gate.gate(None, at=NOW)  # type: ignore[arg-type]
        self.assertEqual(out["reason"], "SUPERVISION_INCOMPLETE")

    def test_empty_ledger_blocks_everything(self):
        gate = SupervisionGate(SupervisionLedger(None))
        out = gate.gate_outlet([ITEM], at=NOW)
        self.assertEqual(out["blocked"][0]["gate_reason"],
                         "SUPERVISION_OUTLET_BYPASS")
        self.assertTrue(out["vetoed"])


class TestAudit(unittest.TestCase):
    def test_jsonl_audit_append_only(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "gate" / "decisions.jsonl"
            gate = SupervisionGate(_approved_ledger(), path)
            gate.gate(ITEM, at=NOW)
            gate.gate(dict(ITEM, knowledge_id="k-999"), at=NOW)
            self.assertEqual(len(gate.decisions()), 2)
            self.assertEqual(len(gate.decisions_for("k-001")), 1)
            lines = path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 2)
            self.assertEqual(json.loads(lines[1])["reason"],
                             "SUPERVISION_OUTLET_BYPASS")

    def test_schema_and_vocab_closed(self):
        self.assertEqual(GATE_SCHEMA, "knowledge-supervision-gate/v1")
        self.assertEqual(set(GATE_CODES),
                         {"SUPERVISION_INCOMPLETE",
                          "SUPERVISION_VERDICT_MISMATCH",
                          "SUPERVISION_OUTLET_BYPASS", "LEDGER_DRIFT"})
        self.assertEqual(set(DECISIONS), {"pass", "block"})
        self.assertTrue(set(GATE_REASONS) >= set(GATE_CODES))


class TestRedline(unittest.TestCase):
    def test_ast_zero_network_zero_subprocess(self):
        banned = {"urllib", "requests", "socket", "http", "subprocess"}
        src = Path(__file__).resolve().parents[1] / "scripts" \
            / "knowledge_supervision_gate.py"
        tree = ast.parse(src.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertFalse(imported & banned, imported & banned)


if __name__ == "__main__":
    unittest.main()
