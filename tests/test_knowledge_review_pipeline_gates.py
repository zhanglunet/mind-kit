# -*- coding: utf-8 -*-
"""PRD-433/T3 测试（trend #2085 的 T3 环节）：知识条目评审流水线 闸门。
运行：uv run --with pytest python -m pytest tests/test_knowledge_review_pipeline.py -q
覆盖：append-only（删/改首条 LEDGER_DRIFT）+verdict 双向对账+coverage 漏判
检出+gate_summary 一票否决+ERROR_CODES 导出。零网络；全合成占位。
"""
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
MOD_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from knowledge_review_pipeline import (  # noqa: E402
    ReviewPipelineLedger, run_pipeline)
from knowledge_review_pipeline_gates import (  # noqa: E402
    ERROR_CODES, append_only_gate, coverage_gate, gate_summary, mark_baseline,
    verdict_gate)

NOW = "2026-11-14T10:00:00Z"
DRAFT = {"draft_id": "d-001", "references": ["R1"], "lines": [
    {"no": 1, "kind": "number", "text": "指标=42（占位）",
     "num": {"stated": 42, "recomputed": 41}},
    {"no": 2, "kind": "text", "text": "本段沿用旧口径（占位）表述"},
    {"no": 3, "kind": "reference", "text": "见 [ref:R1]（占位）与 [ref:R9]（占位）"},
]}


def judge_all_confirm(candidates):
    return [dict(c, verdict="confirmed", note="确认（占位）")
            for c in candidates]


def make_ledger(n=2):
    led = ReviewPipelineLedger(None)
    led.record(run_pipeline(DRAFT, judge_all_confirm, at=NOW))
    led.record(run_pipeline(dict(DRAFT, draft_id="d-002"),
                            judge_all_confirm, at=NOW))
    if n == 1:
        led._records.pop()
    return led


class TestAppendOnlyGate(unittest.TestCase):
    def test_pass_on_intact(self):
        led = make_ledger()
        mark_baseline(led)
        self.assertEqual(append_only_gate(led)["gate"], "pass")

    def test_detect_deletion(self):
        led = make_ledger()
        mark_baseline(led)
        led._records.pop()
        self.assertEqual(append_only_gate(led)["gate"], "LEDGER_DRIFT")

    def test_detect_first_rewrite(self):
        led = make_ledger()
        mark_baseline(led)
        led._records[0]["verdict"] = "pass"
        self.assertEqual(append_only_gate(led)["gate"], "LEDGER_DRIFT")

    def test_non_ledger_object(self):
        self.assertEqual(append_only_gate(object())["gate"], "LEDGER_DRIFT")


class TestVerdictGate(unittest.TestCase):
    def test_pass_on_consistent(self):
        led = make_ledger(1)
        self.assertEqual(verdict_gate(led.entries()[0])["gate"], "pass")

    def test_blocked_without_confirmed(self):
        led = make_ledger(1)
        rec = dict(led.entries()[0], judgments=[])
        self.assertEqual(verdict_gate(rec)["gate"], "REVIEW_VERDICT_MISMATCH")

    def test_pass_with_confirmed(self):
        led = make_ledger(1)
        rec = dict(led.entries()[0], verdict="pass")
        self.assertEqual(verdict_gate(rec)["gate"], "REVIEW_VERDICT_MISMATCH")

    def test_missing_piece_incomplete(self):
        led = make_ledger(1)
        rec = dict(led.entries()[0])
        rec.pop("draft_id")
        self.assertEqual(verdict_gate(rec)["gate"], "REVIEW_INCOMPLETE")

    def test_vocab_out_incomplete(self):
        led = make_ledger(1)
        rec = dict(led.entries()[0], verdict="maybe")
        self.assertEqual(verdict_gate(rec)["gate"], "REVIEW_INCOMPLETE")


class TestCoverageGate(unittest.TestCase):
    def test_pass_on_full(self):
        led = make_ledger(1)
        self.assertEqual(coverage_gate(led.entries()[0])["gate"], "pass")

    def test_detect_missing_judgment(self):
        led = make_ledger(1)
        rec = dict(led.entries()[0])
        rec["judgments"] = rec["judgments"][:-1]
        self.assertEqual(coverage_gate(rec)["gate"], "REVIEW_INCOMPLETE")


class TestGateSummary(unittest.TestCase):
    def test_all_pass(self):
        led = make_ledger()
        mark_baseline(led)
        out = gate_summary([append_only_gate(led),
                            verdict_gate(led.entries()[0])])
        self.assertEqual(out["gate"], "pass")

    def test_one_vote_veto(self):
        led = make_ledger()
        mark_baseline(led)
        led._records.pop()
        out = gate_summary([append_only_gate(led),
                            verdict_gate(make_ledger(1).entries()[0])])
        self.assertEqual(out["gate"], "block")
        self.assertTrue(any("LEDGER_DRIFT" in r for r in out["reasons"]))


class TestErrorCodes(unittest.TestCase):
    def test_error_codes_exported(self):
        self.assertEqual(set(ERROR_CODES),
                         {"LEDGER_DRIFT", "REVIEW_INCOMPLETE",
                          "REVIEW_VERDICT_MISMATCH"})


if __name__ == "__main__":
    unittest.main()
