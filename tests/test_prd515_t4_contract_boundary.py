# -*- coding: utf-8 -*-
"""PRD-515/T4 测试（trend #2498 的 T4 环节）：知识条目技能契约划界断言。
运行：uv run --with pytest python -m pytest tests/test_prd515_t4_contract_boundary.py -q
覆盖（T1 §3 边界）：knowledge_collab_session、knowledge_review_pipeline、knowledge_supervision_bench、wiki 零导入+借鉴词零出现+标准库-only+AST 零网络+
R1 无契约拒绝/R3 Ledger 方法面封闭/schema 封闭/失败显式钉值。零网络；全合成占位。
"""
import ast
import sys
import unittest
from pathlib import Path

MOD_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(MOD_DIR))
from knowledge_skill_contract import (  # noqa: E402
    CONTRACT_SCHEMA, LEGAL_FALLBACK, LEGAL_FAILURE, REQUIRED_KEYS,
    ContractLedger, validate_call)

NOW = "2026-11-17T09:00:00Z"
MODULES = ["knowledge_skill_contract.py", "knowledge_skill_contract_gates.py"]
MOD_DIR = Path(__file__).resolve().parents[1] / "scripts"


class TestBoundary(unittest.TestCase):
    def test_no_downstream_imports(self):
        """knowledge_collab_session、knowledge_review_pipeline、knowledge_supervision_bench、wiki 零导入（含自身闸门反向依赖）。"""
        for mod in MODULES:
            imported = set()
            for node in ast.walk(ast.parse(
                    (MOD_DIR / mod).read_text(encoding="utf-8"))):
                if isinstance(node, ast.Import):
                    imported.update(a.name.split(".")[0] for a in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module.split(".")[0])
            for banned in ("knowledge_collab_session", "knowledge_review_pipeline", "knowledge_supervision_bench", "wiki"):
                self.assertNotIn(banned, imported, f"{mod} 导入 {banned}")
            self.assertNotIn("knowledge_skill_contract_gates" if mod.endswith("gates.py")
                             else "knowledge_skill_contract_gate",
                             imported, f"{mod} 反向依赖闸门")

    def test_borrowed_zero_symbols(self):
        """借鉴仓（ffmpeg-skill/last30days/paper-orchestra/ag-ui）零符号。"""
        for mod in MODULES:
            names = set()
            for node in ast.walk(ast.parse(
                    (MOD_DIR / mod).read_text(encoding="utf-8"))):
                if isinstance(node, ast.Name):
                    names.add(node.id.lower())
                elif isinstance(node, ast.Attribute):
                    names.add(node.attr.lower())
            for word in ("ffmpeg_skill", "last30days", "paper_orchestra",
                         "ag_ui"):
                self.assertNotIn(word, names, f"{mod} 出现 {word}")

    def test_stdlib_only_and_ast_redline(self):
        allowed = {"__future__", "copy", "json", "pathlib", "typing"}
        for mod in MODULES:
            imported = set()
            for node in ast.walk(ast.parse(
                    (MOD_DIR / mod).read_text(encoding="utf-8"))):
                if isinstance(node, ast.Import):
                    imported.update(a.name.split(".")[0] for a in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module.split(".")[0])
            self.assertLessEqual(imported - allowed, set(), mod)
            self.assertFalse(imported & {"urllib", "requests", "socket",
                                         "http", "subprocess"}, mod)


class TestBehaviorPins(unittest.TestCase):
    def test_r1_no_contract_refused(self):
        """R1 无契约的技能不进个人 Wiki（调用被拒绝）。"""
        out = validate_call(None, {})
        self.assertFalse(out["allowed"])
        self.assertEqual(out["reason"], "CONTRACT_MISSING")

    def test_r3_ledger_surface_closed(self):
        led = ContractLedger(None)
        methods = {n for n in dir(led) if not n.startswith("_")}
        self.assertLessEqual(methods, {"record", "entries"}, methods)

    def test_schema_closed(self):
        self.assertEqual(CONTRACT_SCHEMA, "knowledge-skill-contract/v1")
        self.assertEqual(len(REQUIRED_KEYS), 6)
        self.assertEqual(LEGAL_FAILURE, "NOT_COMPUTED")
        self.assertIn("ask_human", LEGAL_FALLBACK)

    def test_failure_always_explicit(self):
        """R3：失败必须显式 NOT_COMPUTED——ledger 的 failure_semantics 字段
        永远记录 NOT_COMPUTED（即使 contract None）。"""
        led = ContractLedger(None)
        led.record(skill_name="x（占位）", call_params={}, contract=None,
                   at=NOW)
        self.assertEqual(led.entries()[-1]["failure_semantics"],
                         "NOT_COMPUTED")


if __name__ == "__main__":
    unittest.main()
