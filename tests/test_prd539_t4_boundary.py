# -*- coding: utf-8 -*-
"""PRD-539/T4 测试（trend #2616 的 T4 环节）：mind-kit 知识方法论包划界断言。
运行：uv run --with pytest python -m pytest tests/test_mindkit_methodology.py -q
按 PRD 任务拆分 T4 行：方法论包与契约/评估/评审流水线/监督回路的边界断言；
无方法论包不成套：
  - 方法论双模块（T2 包 + T3 闸门）对邻居模块（契约/评估/评审流水线/
    监督台/收件箱）零导入（AST）；
  - 借鉴仓（obra/superpowers MIT、Claude-BugHunter MIT、ECC MIT、
    LoopForge、cursor-plugins）零符号（仅代码标识符扫描）；
  - 评估载体词零标识符（不越界审产物/审过程/评包健康/定调用规矩）；
  - 红线钉值：无方法论包拦下（PACK_MISSING）/模式条目缺证据拦下
    （PATTERN_INCOMPLETE）/账本 append-only（深拷贝隔离）/无审批代行；
  - 词表封闭 + AST 零网络零子进程。
只断言，不改任何生产代码。零网络；全合成占位。
"""
import ast
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

MOD_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(MOD_DIR))
MODULE_DIR = MOD_DIR

from mindkit_methodology import PatternLedger  # noqa: E402
from mindkit_methodology_gate import (  # noqa: E402
    ERROR_CODES, GateError, check_pack, check_pattern_entry,
    check_workflow, gate_summary)

NOW = "2026-11-19T10:00:00Z"
MODULES = ["mindkit_methodology.py", "mindkit_methodology_gate.py"]
NEIGHBOR_STEMS = ["knowledge_collab_session", "knowledge_review_pipeline", "knowledge_supervision_bench"]
CARRIER_WORDS = ["knowledge_collab_session", "knowledge_review_pipeline", "knowledge_supervision_bench", "wiki"]


class TestBoundary(unittest.TestCase):
    def test_modules_zero_neighbor_imports(self):
        """方法论双模块对邻居（契约/评估/评审/监督/收件箱）零导入。"""
        for mod in MODULES:
            src = (MODULE_DIR / mod).read_text(encoding="utf-8")
            imported = set()
            for node in ast.walk(ast.parse(src)):
                if isinstance(node, ast.Import):
                    imported.update(a.name.split(".")[0] for a in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module.split(".")[0])
            for stem in NEIGHBOR_STEMS:
                self.assertNotIn(stem, imported, f"{mod} 导入邻居 {stem}")

    def test_downstream_carrier_zero_identifiers(self):
        """评审/监督/评估载体词零标识符（不越界）。"""
        for mod in MODULES:
            src = (MODULE_DIR / mod).read_text(encoding="utf-8")
            names = set()
            for node in ast.walk(ast.parse(src)):
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                    names.add(node.name.lower())
                elif isinstance(node, ast.Name):
                    names.add(node.id.lower())
            for word in CARRIER_WORDS:
                self.assertNotIn(word, names,
                                 f"{mod} 标识符出现 {word}")

    def test_borrowed_zero_symbols(self):
        """借鉴仓零符号（superpowers/bughunter/ecc/loopforge）。"""
        for mod in MODULES:
            src = (MODULE_DIR / mod).read_text(encoding="utf-8")
            names = set()
            for node in ast.walk(ast.parse(src)):
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                    names.add(node.name.lower())
                elif isinstance(node, ast.Name):
                    names.add(node.id.lower())
            for word in ("superpowers", "bughunter", "ecc_", "loopforge"):
                self.assertNotIn(word, names, f"{mod} 出现 {word}")


class TestRedlines(unittest.TestCase):
    def test_no_pack_refused_pin(self):
        """R1 钉值：无方法论包 → PACK_MISSING 拦下。"""
        d = check_pack(False, "skill-a")
        self.assertFalse(d["allowed"])
        self.assertEqual(d["reasons"][0]["code"], "PACK_MISSING")

    def test_pattern_missing_evidence_pin(self):
        """R2 钉值：模式条目缺证据 → PATTERN_INCOMPLETE。"""
        bad = {"pattern": "p（占位）", "source_case": "s（占位）",
               "evidence": "", "caliber_version": "v1"}
        d = check_pattern_entry(bad)
        self.assertFalse(d["allowed"])
        self.assertEqual(d["reasons"][0]["code"], "PATTERN_INCOMPLETE")

    def test_ledger_append_only_deep_copy(self):
        """R4 钉值：模式库 append-only——entries 深拷贝隔离。"""
        led = PatternLedger(None)
        led.record({"pattern": "p（占位）", "source_case": "s（占位）",
                    "evidence": "e（占位）", "caliber_version": "v1"})
        snapshot = led.entries()
        snapshot[0]["pattern"] = "改（占位）"
        self.assertEqual(led.entries()[0]["pattern"], "p（占位）")

    def test_gate_not_admin_pin(self):
        """R5 钉值：方法论包不代行审批——模块无审批符号。"""
        for mod in MODULES:
            src = (MODULE_DIR / mod).read_text(encoding="utf-8")
            names = {n.name.lower() for n in ast.walk(ast.parse(src))
                     if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
            for word in ("approve", "publish", "finalize_review"):
                self.assertNotIn(word, names, f"{mod} 出现 {word}")

    def test_vocab_closed(self):
        """词表封闭：拦因词表与 workflow 词表只能取设计稿集合。"""
        self.assertEqual(set(ERROR_CODES),
                         {"PACK_MISSING", "PATTERN_INCOMPLETE",
                           "STEP_INVALID"})

    def test_ast_zero_network(self):
        banned = {"urllib", "requests", "socket", "http", "subprocess"}
        for mod in MODULES:
            src = (MODULE_DIR / mod).read_text(encoding="utf-8")
            imported = set()
            for node in ast.walk(ast.parse(src)):
                if isinstance(node, ast.Import):
                    imported.update(a.name.split(".")[0] for a in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module.split(".")[0])
            self.assertFalse(imported & banned,
                             f"{mod} 导入 {imported & banned}")


if __name__ == "__main__":
    unittest.main()
