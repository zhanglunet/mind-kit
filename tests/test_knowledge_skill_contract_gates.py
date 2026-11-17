# -*- coding: utf-8 -*-
"""PRD-515/T3 测试（trend #2497 的 T3 环节）：知识条目技能契约闸门。
运行：uv run --with pytest python -m pytest tests/test_knowledge_skill_contract_gates.py -q
"""
import sys
import unittest
from pathlib import Path

MOD_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(MOD_DIR))
from knowledge_skill_contract import ContractLedger  # noqa: E402
from knowledge_skill_contract_gates import (  # noqa: E402
    ERROR_CODES, append_only_gate, gate_summary, mark_baseline)

NOW = "2026-11-17T10:00:00Z"


def make_ledger(n=2):
    led = ContractLedger(None)
    for i in range(n):
        led.record(skill_name=f"skill-{i}（占位）",
                   call_params={"input": "…（占位）"}, contract=None, at=NOW)
    return led


class TestGates(unittest.TestCase):
    def test_append_only_pass(self):
        led = make_ledger()
        mark_baseline(led)
        self.assertEqual(append_only_gate(led)["gate"], "pass")

    def test_append_only_detect_deletion(self):
        led = make_ledger()
        mark_baseline(led)
        led._entries.pop()
        self.assertEqual(append_only_gate(led)["gate"], "LEDGER_DRIFT")

    def test_append_only_detect_rewrite(self):
        led = make_ledger()
        mark_baseline(led)
        led._entries[0]["skill_name"] = "改（占位）"
        self.assertEqual(append_only_gate(led)["gate"], "LEDGER_DRIFT")

    def test_non_ledger(self):
        self.assertEqual(append_only_gate(object())["gate"], "LEDGER_DRIFT")

    def test_summary_all_pass(self):
        led = make_ledger()
        mark_baseline(led)
        out = gate_summary([append_only_gate(led)])
        self.assertEqual(out["gate"], "pass")

    def test_summary_one_vote_veto(self):
        led = make_ledger()
        mark_baseline(led)
        led._entries.pop()
        out = gate_summary([append_only_gate(led)])
        self.assertEqual(out["gate"], "block")

    def test_error_codes_exported(self):
        self.assertEqual(set(ERROR_CODES), {"LEDGER_DRIFT"})


if __name__ == "__main__":
    unittest.main()
