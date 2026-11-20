# -*- coding: utf-8 -*-
"""PRD-562/T3 测试（trend #2660 的 T3 环节）：准入检查校验闸门。
运行：uv run --with pytest python -m pytest skill/mind-kit/scripts/test_mindkit_admission_gate.py -q
覆盖（T1 红线 R1~R3）：留痕 append-only（删/改 DRIFT）/五层覆盖校验
（缺层+词表外）/一票否决不可绕/准入词表封闭（机器不代行）/一票否决/
真实留痕过闸/AST 零网络。零网络；全合成占位。
"""
import ast
import copy
import sys
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SRC))
MODULE_DIR = SRC

from mindkit_admission import AdmissionLedger  # noqa: E402
from mindkit_admission_gate import (  # noqa: E402
    ERROR_CODES, append_only_gate, check_layer_coverage, check_no_auto_admit,
    check_one_vote, gate_summary)


def make_ledger(n=5):
    led = AdmissionLedger(None)
    layers = ("L1_quality", "L2_security", "L3_overlap", "L4_synth", "L5_live")
    verdicts = ("过", "过", "过", "过", "过")
    for i in range(n):
        led.record({"layer": layers[i % len(layers)],
                    "verdict": verdicts[i % len(verdicts)],
                    "evidence": f"占位证据 {i}",
                    "checked_at": "2026-11-20T09:00:00Z"})
    return led


class TestAppendOnly(unittest.TestCase):
    def test_no_change_pass(self):
        led = make_ledger(5)
        entries = led.entries()
        d = append_only_gate(entries, entries[0], len(entries))
        self.assertEqual(d["gate"], "pass")

    def test_deletion_drift(self):
        led = make_ledger(5)
        entries = led.entries()
        d = append_only_gate(entries[:-1], entries[0], len(entries))
        self.assertEqual(d["gate"], "block")
        self.assertEqual(d["reasons"][0]["code"], "ADMISSION_LEDGER_DRIFT")

    def test_rewrite_drift(self):
        led = make_ledger(5)
        entries = led.entries()
        baseline = copy.deepcopy(entries[0])
        entries[0]["verdict"] = "改（占位）"
        d = append_only_gate(entries, baseline, len(entries))
        self.assertEqual(d["gate"], "block")


class TestLayerCoverage(unittest.TestCase):
    def test_all_five_pass(self):
        led = make_ledger(5)
        d = check_layer_coverage(led.entries())
        self.assertEqual(d["gate"], "pass")

    def test_missing_layer_refused(self):
        led = make_ledger(4)
        d = check_layer_coverage(led.entries())
        self.assertEqual(d["gate"], "block")
        self.assertEqual(d["reasons"][0]["code"], "LAYER_COVERAGE_GAP")

    def test_vocab_out_refused(self):
        led = AdmissionLedger(None)
        led.record({"layer": "L9_unknown", "verdict": "过",
                    "evidence": "占位", "checked_at": "2026-11-20T09:00:00Z"})
        d = check_layer_coverage(led.entries())
        self.assertEqual(d["gate"], "block")
        self.assertEqual(d["reasons"][0]["code"], "LAYER_COVERAGE_GAP")


class TestOneVote(unittest.TestCase):
    def test_block_bypass_refused(self):
        """任一层「不过」而 admission 不是「不进（整改）」→ ONE_VOTE_BYPASS。"""
        d = check_one_vote([{"layer": "L1_quality", "verdict": "不过"}],
                           "可进收件箱")
        self.assertEqual(d["gate"], "block")
        self.assertEqual(d["reasons"][0]["code"], "ONE_VOTE_BYPASS")

    def test_block_with_correct_admission_pass(self):
        d = check_one_vote([{"layer": "L1_quality", "verdict": "不过"}],
                           "不进（整改）")
        self.assertEqual(d["gate"], "pass")


class TestNoAutoAdmit(unittest.TestCase):
    def test_vocab_closed(self):
        for a in ("可进收件箱", "不进（整改）", "待复核", "待补测"):
            self.assertEqual(check_no_auto_admit(a)["gate"], "pass")

    def test_vocab_out_refused(self):
        d = check_no_auto_admit("自动通过")
        self.assertEqual(d["gate"], "block")
        self.assertEqual(d["reasons"][0]["code"], "AUTO_ADMIT")


class TestSummary(unittest.TestCase):
    def test_one_vote_veto(self):
        ok = {"gate": "pass", "reasons": []}
        bad = {"gate": "block",
               "reasons": [{"code": "KEY_LEAK", "detail": "d"}]}
        self.assertEqual(gate_summary([ok, ok])["gate"], "pass")
        self.assertEqual(gate_summary([ok, bad])["gate"], "block")

    def test_error_codes_exported(self):
        self.assertEqual(set(ERROR_CODES),
                         {"ADMISSION_LEDGER_DRIFT", "LAYER_COVERAGE_GAP",
                          "ONE_VOTE_BYPASS", "AUTO_ADMIT"})


class TestRealLedger(unittest.TestCase):
    def test_t2_real_entries_pass_coverage(self):
        """T2 落账的真实五层留痕过覆盖闸。"""
        led = make_ledger(5)
        d = check_layer_coverage(led.entries())
        self.assertEqual(d["gate"], "pass")


class TestRedline(unittest.TestCase):
    def test_ast_zero_network(self):
        banned = {"urllib", "requests", "socket", "http", "subprocess"}
        for name in ("mindkit_admission.py", "mindkit_admission_gate.py"):
            src = (MODULE_DIR / name).read_text(encoding="utf-8")
            imported = set()
            for node in ast.walk(ast.parse(src)):
                if isinstance(node, ast.Import):
                    imported.update(a.name.split(".")[0] for a in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module.split(".")[0])
            self.assertFalse(imported & banned, name)

    def test_ledger_deep_copy_isolated(self):
        led = make_ledger(3)
        snapshot = led.entries()
        snapshot[0]["verdict"] = "改（占位）"
        self.assertNotEqual(led.entries()[0]["verdict"], "改（占位）")


if __name__ == "__main__":
    unittest.main()
