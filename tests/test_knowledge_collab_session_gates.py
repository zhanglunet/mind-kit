 # -*- coding: utf-8 -*-
"""PRD-410/T3 测试（trend #1970 的 T3 环节）：知识共建会话 闸门。
运行：uv run --with pytest python -m pytest tests/test_knowledge_collab_session.py -q
覆盖：append-only 复核（删/改首条 LEDGER_DRIFT）+accept_gate 双向对账+
outlet_gate 拦截+gate_summary 一票否决+ERROR_CODES 导出。零网络；全合成占位。
"""
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
MOD_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from knowledge_collab_session import CollabSessionLedger  # noqa: E402
from knowledge_collab_session_gates import (  # noqa: E402
    ERROR_CODES, accept_gate, append_only_gate, gate_summary, mark_baseline,
    outlet_gate)

NOW = "2026-11-13T10:00:00Z"


def make_ledger(n_accepted=1):
    led = CollabSessionLedger(None)
    led.propose_change("e-001", "intake", "editor-a（占位）", NOW,
                       {"change": "入库条目（占位）"})
    led.propose_change("e-002", "revision", "agent-a（占位）", NOW,
                       {"change": "修订建议（占位）"})
    if n_accepted:
        led.accept_change("e-001", "editor-b（占位）", NOW)
    return led


class TestAppendOnlyGate(unittest.TestCase):
    def test_pass_on_intact(self):
        led = make_ledger()
        mark_baseline(led)
        self.assertEqual(append_only_gate(led)["gate"], "pass")

    def test_detect_deletion(self):
        led = make_ledger()
        mark_baseline(led)
        led._events.pop()
        self.assertEqual(append_only_gate(led)["gate"], "LEDGER_DRIFT")

    def test_detect_first_rewrite(self):
        led = make_ledger()
        mark_baseline(led)
        led._events[0]["author"] = "被改（占位）"
        self.assertEqual(append_only_gate(led)["gate"], "LEDGER_DRIFT")

    def test_non_ledger_object(self):
        self.assertEqual(append_only_gate(object())["gate"], "LEDGER_DRIFT")


class TestAcceptGate(unittest.TestCase):
    def test_pass_on_consistent(self):
        self.assertEqual(accept_gate(make_ledger())["gate"], "pass")

    def test_accept_missing_attribution(self):
        led = make_ledger()
        led._events[-1]["author"] = ""
        self.assertEqual(accept_gate(led)["gate"], "SESSION_INCOMPLETE")


class TestOutletGate(unittest.TestCase):
    def test_pass_on_clean_outlet(self):
        led = make_ledger()
        out = led.outlet([{"entry_id": "e-001"}])
        self.assertEqual(outlet_gate(out)["gate"], "pass")

    def test_blocked_mixed_into_accepted(self):
        led = make_ledger()
        entry = {"entry_id": "e-002"}
        out = led.outlet([entry])
        out["accepted"].append(entry)   # 人为混入被拦条目
        self.assertEqual(outlet_gate(out)["gate"], "SESSION_STATE_CONFLICT")


class TestGateSummary(unittest.TestCase):
    def test_all_pass(self):
        led = make_ledger()
        mark_baseline(led)
        out = gate_summary([append_only_gate(led), accept_gate(led)])
        self.assertEqual(out["gate"], "pass")

    def test_one_vote_veto(self):
        led = make_ledger()
        mark_baseline(led)
        led._events.pop()
        out = gate_summary([append_only_gate(led), accept_gate(led)])
        self.assertEqual(out["gate"], "block")
        self.assertTrue(any("LEDGER_DRIFT" in r for r in out["reasons"]))


class TestErrorCodes(unittest.TestCase):
    def test_error_codes_exported(self):
        self.assertEqual(set(ERROR_CODES),
                         {"LEDGER_DRIFT", "SESSION_INCOMPLETE",
                          "SESSION_STATE_CONFLICT"})


if __name__ == "__main__":
    unittest.main()
