 # -*- coding: utf-8 -*-
"""PRD-410/T2 测试（trend #1970 的 T2 环节）：知识共建会话。
运行：uv run --with pytest python -m pytest tests/test_knowledge_collab_session.py -q
覆盖（T1 §4 + R1~R4）：propose 署名校验/状态机单向/outlet 拦截/JSONL 落库/
replay 确定性/词表封闭/AST 零网络。零网络；全合成占位。
"""
import ast
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
MOD_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from knowledge_collab_session import (  # noqa: E402
    ERROR_CODES,
    EVENTS,
    STATUSES,
    CollabSessionLedger,
    SessionError,
    replay,
)

NOW = "2026-11-13T09:00:00Z"


def mk_ledger(path=None):
    led = CollabSessionLedger(path)
    led.propose_change("e-001", "intake", "editor-a（占位）", NOW,
                       {"target": "知识[9]（占位）", "change": "入库条目（占位）"})
    led.propose_change("e-002", "revision", "agent-a（占位）", NOW,
                       {"target": "知识[9]修订（占位）", "change": "修订建议（占位）"})
    return led


class TestPropose(unittest.TestCase):
    def test_propose_attributed(self):
        led = mk_ledger()
        ev = led.events()[0]
        self.assertEqual((ev["author"], ev["at"], ev["status"]),
                         ("editor-a（占位）", NOW, "proposed"))
        self.assertEqual(ev["schema"], "knowledge-collab-session/v1")

    def test_propose_incomplete_refused(self):
        led = CollabSessionLedger(None)
        with self.assertRaisesRegex(SessionError, "SESSION_INCOMPLETE"):
            led.propose_change("e-001", "intake", "", NOW)

    def test_vocab_closed(self):
        self.assertEqual(set(EVENTS), {"propose", "accept", "reject"})
        self.assertEqual(set(STATUSES),
                         {"proposed", "accepted", "rejected"})


class TestStateMachine(unittest.TestCase):
    def test_accept_flow(self):
        led = mk_ledger()
        led.accept_change("e-001", "editor-b（占位）", NOW)
        self.assertEqual(led.statuses()["e-001"], "accepted")

    def test_double_accept_conflict(self):
        led = mk_ledger()
        led.accept_change("e-001", "editor-b（占位）", NOW)
        with self.assertRaisesRegex(SessionError, "SESSION_STATE_CONFLICT"):
            led.accept_change("e-001", "editor-b（占位）", NOW)

    def test_accept_unknown_conflict(self):
        led = mk_ledger()
        with self.assertRaisesRegex(SessionError, "SESSION_STATE_CONFLICT"):
            led.accept_change("e-999", "editor-b（占位）", NOW)

    def test_reject_then_accept_conflict(self):
        led = mk_ledger()
        led.reject_change("e-002", "editor-b（占位）", NOW, "误改（占位）")
        with self.assertRaisesRegex(SessionError, "SESSION_STATE_CONFLICT"):
            led.accept_change("e-002", "editor-b（占位）", NOW)


class TestOutlet(unittest.TestCase):
    def test_outlet_blocks_unaccepted(self):
        led = mk_ledger()
        led.accept_change("e-001", "editor-b（占位）", NOW)
        entries = [{"entry_id": "e-001", "change": "入库条目（占位）"},
                   {"entry_id": "e-002", "change": "修订建议（占位）"}]
        out = led.outlet(entries)
        self.assertEqual([e["entry_id"] for e in out["accepted"]], ["e-001"])
        self.assertEqual(out["blocked_count"], 1)
        self.assertEqual(out["blocked"][0]["status"], "proposed")


class TestLedgerAndReplay(unittest.TestCase):
    def test_jsonl_persistence_append_only(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "session" / "log.jsonl"
            led = mk_ledger(path)
            led.accept_change("e-001", "editor-b（占位）", NOW)
            lines = path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 3)
            self.assertEqual(json.loads(lines[-1])["event"], "accept")

    def test_replay_deterministic(self):
        led = mk_ledger()
        evs = led.events()
        self.assertEqual(replay(evs), replay(list(evs)))
        self.assertEqual(led.statuses(), replay(evs))


class TestRedline(unittest.TestCase):
    def test_ast_zero_network_zero_subprocess(self):
        banned = {"urllib", "requests", "socket", "http", "subprocess"}
        src = MOD_DIR / "knowledge_collab_session.py"
        tree = ast.parse(Path(src).read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertFalse(imported & banned, imported & banned)

    def test_error_codes_closed(self):
        self.assertEqual(set(ERROR_CODES),
                         {"SESSION_INCOMPLETE", "SESSION_STATE_CONFLICT"})


if __name__ == "__main__":
    unittest.main()
