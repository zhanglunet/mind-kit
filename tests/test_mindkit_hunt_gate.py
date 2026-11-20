# -*- coding: utf-8 -*-
"""PRD-585/T3 测试（trend #2937 的 T3 环节）：巡检校验闸门。
运行：uv run --with pytest python -m pytest tests/test_mindkit_hunt_gate.py -q
覆盖：append-only 复核/复现证据可验证（REPRO_MISSING）/误报复核一票否决
（FP_ADMIT）/结论词表封闭/gate_summary 多闸一票否决/ERROR_CODES 封闭/
T2 留痕真实条目过闸（集成）。零网络；全合成占位。
"""
import sys
import unittest
from pathlib import Path

MOD_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(MOD_DIR))
MODULE_DIR = MOD_DIR

from mindkit_hunt import FindingLedger  # noqa: E402
from mindkit_hunt_gate import (  # noqa: E402
    ERROR_CODES, append_only_gate, check_fp_veto, check_hunt_vocab,
    check_repro_evidence, gate_summary)


def _entry(over=None):
    e = {"finding": "S_占位：命中（占位）", "repro": "复现",
         "evidence": "命中（占位）", "found_at": "2026-11-20T09:00:00Z"}
    if over:
        e.update(over)
    return e


class TestAppendOnly(unittest.TestCase):
    def test_equal_passes(self):
        es = [_entry()]
        self.assertEqual(append_only_gate(es, es[0], len(es))["gate"], "pass")

    def test_deletion_refused(self):
        es = [_entry(), _entry(over={"finding": "S_占位2"})]
        d = append_only_gate(es[1:], es[0], len(es))
        self.assertEqual(d["gate"], "block")
        self.assertEqual(d["reasons"][0]["code"], "FINDING_LEDGER_DRIFT")

    def test_rewrite_refused(self):
        es = [_entry()]
        altered = [dict(es[0], finding="改（占位）")]
        d = append_only_gate(altered, es[0], len(es))
        self.assertEqual(d["gate"], "block")


class TestRepro(unittest.TestCase):
    def test_all_repro_passes(self):
        self.assertEqual(check_repro_evidence([_entry()])["gate"], "pass")

    def test_missing_repro_refused(self):
        d = check_repro_evidence([_entry(over={"repro": "未复现"})])
        self.assertEqual(d["reasons"][0]["code"], "REPRO_MISSING")

    def test_empty_evidence_refused(self):
        d = check_repro_evidence([_entry(over={"evidence": ""})])
        self.assertEqual(d["reasons"][0]["code"], "REPRO_MISSING")


class TestFpVeto(unittest.TestCase):
    def test_clean_passes(self):
        self.assertEqual(check_fp_veto([_entry()])["gate"], "pass")

    def test_fp_refused(self):
        """误报复核一票否决：误报条目未摘除 → FP_ADMIT。"""
        d = check_fp_veto([_entry(over={"review": "误报"})])
        self.assertEqual(d["gate"], "block")
        self.assertEqual(d["reasons"][0]["code"], "FP_ADMIT")


class TestVocab(unittest.TestCase):
    def test_conclusions_pass(self):
        for h in ("有发现", "无可复现发现"):
            self.assertEqual(check_hunt_vocab(h)["gate"], "pass", h)

    def test_outside_refused(self):
        d = check_hunt_vocab("自动裁决")
        self.assertEqual(d["reasons"][0]["code"], "HUNT_VOCAB_GAP")

    def test_error_codes_closed(self):
        self.assertEqual(set(ERROR_CODES),
                         {"FINDING_LEDGER_DRIFT", "REPRO_MISSING",
                          "FP_ADMIT", "HUNT_VOCAB_GAP"})


class TestSummary(unittest.TestCase):
    def test_one_vote(self):
        ok = gate_summary([check_hunt_vocab("有发现")])
        self.assertEqual(ok["gate"], "pass")
        bad = gate_summary([check_hunt_vocab("有发现"),
                            check_fp_veto([_entry(over={"review": "误报"})])])
        self.assertEqual(bad["gate"], "block")


class TestIntegration(unittest.TestCase):
    def test_t2_ledger_entry_passes_gates(self):
        led = FindingLedger(None)
        rec = led.record(_entry())
        self.assertEqual(check_repro_evidence([rec])["gate"], "pass")
        self.assertEqual(check_fp_veto([rec])["gate"], "pass")


if __name__ == "__main__":
    unittest.main()
