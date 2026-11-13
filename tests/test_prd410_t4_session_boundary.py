 # -*- coding: utf-8 -*-
"""PRD-410/T4 测试（trend #1970 的 T4 环节）：知识共建会话 划界断言。
运行：uv run --with pytest python -m pytest tests/test_knowledge_collab_session.py -q
覆盖（T1 §0/§3，验收「划界断言通过」）：会话面零触碰下游载体（knowledge_verify_bench、wiki、store
零导入）+借鉴词零出现（仅代码标识符扫描）+标准库-only 钉值+零网络 AST
+R1 出口拦截钉值+R2 署名钉值+R3 append-only 方法面封闭+回放确定性+R4
状态机钉值。零网络；全合成占位。
"""
import ast
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
MOD_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from knowledge_collab_session import (  # noqa: E402
    ERROR_CODES, EVENTS, STATUSES, CollabSessionLedger, SessionError, replay)

NOW = "2026-11-13T11:00:00Z"
SESSION_MODULES = ["knowledge_collab_session.py", "knowledge_collab_session_gates.py"]


def _imports_of(path: Path) -> set:
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    return imported


def _code_names(path: Path) -> set:
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
    return names


def mk():
    led = CollabSessionLedger(None)
    led.propose_change("e-001", "intake", "editor-a（占位）", NOW,
                       {"change": "入库条目（占位）"})
    return led


class TestModuleIsolation(unittest.TestCase):
    def test_session_never_imports_downstream_carriers(self):
        """会话面零触碰下游载体（knowledge_verify_bench、wiki、store 零导入——被消费面只可上行不可下行）。"""
        for mod in SESSION_MODULES:
            imported = _imports_of(MOD_DIR / mod)
            for banned in ["knowledge_verify_bench", "wiki", "store"]:
                self.assertNotIn(banned, imported, f"{mod} 导入 {banned}")

    def test_upstream_zero_symbols(self):
        """借鉴仓（zed 双证含 GPL-3.0/agent-browser/agent-desktop Apache-2.0/
        OpenBot MIT 实测）零符号——只借协作形态（仅代码标识符扫描，
        docstring 提及不算）。"""
        for mod in SESSION_MODULES:
            names = {n.lower() for n in _code_names(MOD_DIR / mod)}
            for word in ("zed", "agent_browser", "agent_desktop", "openbot"):
                self.assertNotIn(word, names, f"{mod} 出现 {word}")

    def test_stdlib_only_and_redline_ast(self):
        """标准库-only 钉值：session 静态导入全标准库；零网络零子进程。"""
        imported = _imports_of(MOD_DIR / "knowledge_collab_session.py")
        self.assertLessEqual(imported - {"__future__", "copy", "json",
                                         "pathlib", "typing"}, set(),
                             imported)
        for mod in SESSION_MODULES:
            imported = _imports_of(MOD_DIR / mod)
            self.assertFalse(imported & {"urllib", "requests", "socket",
                                         "http", "subprocess"},
                             f"{mod} 导入网络/子进程")


class TestRedLinePins(unittest.TestCase):
    def test_r1_unaccepted_blocked_at_outlet(self):
        """R1 拦截钉值：proposed/rejected 不进出口 accepted。"""
        led = mk()
        led.reject_change("e-001", "editor-b（占位）", NOW, "误改（占位）")
        out = led.outlet([{"entry_id": "e-001"}])
        self.assertEqual(out["accepted"], [])
        self.assertEqual(out["blocked_count"], 1)

    def test_r2_attribution_pin(self):
        """R2 署名钉值：缺 author/at 的事件拒绝入账。"""
        led = CollabSessionLedger(None)
        with self.assertRaisesRegex(SessionError, "SESSION_INCOMPLETE"):
            led.propose_change("e-001", "intake", "", NOW)

    def test_r3_surface_closed_and_replay_deterministic(self):
        """R3：Ledger 方法面封闭（零删除/改写方法）+回放确定性。"""
        led = mk()
        methods = {n for n in dir(led) if not n.startswith("_")}
        self.assertLessEqual(methods, {"propose_change", "accept_change",
                                       "reject_change", "events", "statuses",
                                       "outlet", "replay_from_log"}, methods)
        evs = led.events()
        self.assertEqual(replay(list(evs)), replay(list(evs)))

    def test_r4_state_machine_pin(self):
        """R4：proposed→accepted/rejected 单向；词表封闭。"""
        led = mk()
        led.accept_change("e-001", "editor-b（占位）", NOW)
        with self.assertRaisesRegex(SessionError, "SESSION_STATE_CONFLICT"):
            led.reject_change("e-001", "editor-b（占位）", NOW)
        self.assertEqual(set(EVENTS), {"propose", "accept", "reject"})
        self.assertEqual(set(ERROR_CODES),
                         {"SESSION_INCOMPLETE", "SESSION_STATE_CONFLICT"})
        self.assertEqual(set(STATUSES),
                         {"proposed", "accepted", "rejected"})


if __name__ == "__main__":
    unittest.main()
