# -*- coding: utf-8 -*-
"""PRD-539/T3 测试（trend #2615 的 T3 环节）：mind-kit 知识方法论包方法论包校验闸门。
运行：uv run --with pytest python -m pytest tests/test_mindkit_methodology_gate.py -q
覆盖（T1 红线 R1~R4）：PACK_MISSING 拦下/PATTERN_INCOMPLETE 四件缺一拦下/
STEP_INVALID 跳步乱步多步拦下/一票否决/真实模式条目过闸（T2 落账回读）/
AST 零网络/无审批代行。零网络；全合成占位 + 真实文件只读。
"""
import ast
import json
import sys
import tempfile
import unittest
from pathlib import Path

MOD_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(MOD_DIR))
MODULE_DIR = MOD_DIR

from mindkit_methodology_gate import (  # noqa: E402
    ERROR_CODES, GATE_SCHEMA, GateError, check_pack, check_pattern_entry,
    check_workflow, enforce_pack, gate_summary)
from mindkit_methodology import PatternLedger  # noqa: E402

NOW = "2026-11-19T10:00:00Z"


def _entry():
    return {"pattern": "测试模式（占位）", "source_case": "真实案例（占位）",
            "evidence": "docs/plans（占位）", "caliber_version": "v1"}


class TestPackGate(unittest.TestCase):
    def test_pack_missing_refused(self):
        d = check_pack(False, "skill-a")
        self.assertFalse(d["allowed"])
        self.assertEqual(d["reasons"][0]["code"], "PACK_MISSING")

    def test_pack_present_allowed(self):
        self.assertTrue(check_pack(True, "skill-a")["allowed"])

    def test_enforce_pack_raises(self):
        with self.assertRaisesRegex(GateError, "GATE_BLOCKED"):
            enforce_pack(False, "skill-a")


class TestPatternGate(unittest.TestCase):
    def test_complete_entry_allowed(self):
        self.assertTrue(check_pattern_entry(_entry())["allowed"])

    def test_missing_field_refused(self):
        for key in ("pattern", "source_case", "evidence", "caliber_version"):
            bad = _entry()
            del bad[key]
            d = check_pattern_entry(bad)
            self.assertFalse(d["allowed"])
            self.assertEqual(d["reasons"][0]["code"], "PATTERN_INCOMPLETE")

    def test_non_dict_refused(self):
        d = check_pattern_entry("x")
        self.assertFalse(d["allowed"])
        self.assertEqual(d["reasons"][0]["code"], "PATTERN_INCOMPLETE")


class TestWorkflowGate(unittest.TestCase):
    def test_full_sequence_allowed(self):
        self.assertTrue(check_workflow(["采来源", "抽知识", "复核", "入库", "复用"])["allowed"])

    def test_skip_refused(self):
        d = check_workflow(["采来源", "抽知识", "复核", "入库", "复用"][:1] + ["采来源", "抽知识", "复核", "入库", "复用"][2:])
        self.assertFalse(d["allowed"])
        self.assertEqual(d["reasons"][0]["code"], "STEP_INVALID")

    def test_extra_refused(self):
        d = check_workflow(["采来源", "抽知识", "复核", "入库", "复用"] + ["多余步（占位）"])
        self.assertFalse(d["allowed"])
        self.assertEqual(d["reasons"][0]["code"], "STEP_INVALID")


class TestSummary(unittest.TestCase):
    def test_one_vote_veto(self):
        out = gate_summary([check_pack(True), check_pattern_entry(_entry()),
                            check_workflow(["采来源", "抽知识", "复核", "入库", "复用"])])
        self.assertEqual(out["gate"], "pass")
        out = gate_summary([check_pack(True), check_pack(False)])
        self.assertEqual(out["gate"], "block")
        self.assertEqual(len(out["reasons"]), 1)

    def test_error_codes_exported(self):
        self.assertEqual(set(ERROR_CODES),
                         {"PACK_MISSING", "PATTERN_INCOMPLETE",
                           "STEP_INVALID"})


class TestRealLedger(unittest.TestCase):
    def test_t2_pattern_entry_passes_gate(self):
        """T2 落账的首份模式条目（真实文件）过闸。"""
        led = PatternLedger(None)
        rec = led.record(_entry())
        self.assertTrue(check_pattern_entry(rec)["allowed"])


class TestRedline(unittest.TestCase):
    def test_ast_zero_network(self):
        banned = {"urllib", "requests", "socket", "http", "subprocess"}
        for name in ("mindkit_methodology.py", "mindkit_methodology_gate.py"):
            src = (MODULE_DIR / name).read_text(encoding="utf-8")
            imported = set()
            for node in ast.walk(ast.parse(src)):
                if isinstance(node, ast.Import):
                    imported.update(a.name.split(".")[0] for a in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module.split(".")[0])
            self.assertFalse(imported & banned, name)

    def test_no_approve_path(self):
        for name in ("mindkit_methodology.py", "mindkit_methodology_gate.py"):
            src = (MODULE_DIR / name).read_text(encoding="utf-8")
            tree = ast.parse(src)
            names = {n.name.lower() for n in ast.walk(tree)
                     if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
            for word in ("approve", "publish", "finalize_review"):
                self.assertNotIn(word, names, f"{name} 出现 {word}")


if __name__ == "__main__":
    unittest.main()
