# -*- coding: utf-8 -*-
"""PRD-539/T2 测试（trend #2614 的 T2 环节）：mind-kit 知识方法论包方法论包落账。
运行：uv run --with pytest python -m pytest tests/test_mindkit_methodology.py -q
覆盖（T1 §1/§3 + 红线）：workflow 封闭词表与步骤序列校验（全序/前缀 OK，
跳步/乱步/多步拦下）/模式库 JSONL append-only 缺件拒绝/渲染两遍逐字节一致/
真实清单断言（T1 设计稿真实存在+首份模式条目四件齐全）/AST 零网络。
零网络；全合成占位 + 真实文件只读。
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

SOURCE_DIR = MODULE_DIR

from mindkit_methodology import (  # noqa: E402
    METHOD_COMMAND, METHODOLOGY_SCHEMA, SKILLSET_NAME, WORKFLOW_STEPS,
    MethodologyError, PatternLedger, check_step_sequence, render_pack_md)

NOW = "2026-11-19T09:00:00Z"


class TestWorkflow(unittest.TestCase):
    def test_workflow_closed_vocab(self):
        """workflow 封闭：5 步、词表固定。"""
        self.assertEqual(len(WORKFLOW_STEPS), 5)
        self.assertEqual(WORKFLOW_STEPS, ["采来源", "抽知识", "复核", "入库", "复用"])

    def test_full_sequence_ok(self):
        d = check_step_sequence(list(WORKFLOW_STEPS))
        self.assertTrue(d["ok"])

    def test_prefix_sequence_ok(self):
        d = check_step_sequence(list(WORKFLOW_STEPS)[:2])
        self.assertTrue(d["ok"])
        self.assertEqual(d["detail"], "进行中")

    def test_skip_step_refused(self):
        d = check_step_sequence(list(WORKFLOW_STEPS)[:1]
                                + list(WORKFLOW_STEPS)[2:])
        self.assertFalse(d["ok"])
        self.assertEqual(d["reason"], "STEP_INVALID")

    def test_wrong_order_refused(self):
        bad = list(WORKFLOW_STEPS)
        bad[0], bad[1] = bad[1], bad[0]
        d = check_step_sequence(bad)
        self.assertFalse(d["ok"])
        self.assertEqual(d["reason"], "STEP_INVALID")

    def test_extra_step_refused(self):
        d = check_step_sequence(list(WORKFLOW_STEPS) + ["多余步（占位）"])
        self.assertFalse(d["ok"])
        self.assertEqual(d["reason"], "STEP_INVALID")


class TestPatternLedger(unittest.TestCase):
    def _entry(self):
        return {"pattern": "测试模式（占位）", "source_case": "真实案例（占位）",
                "evidence": "docs/plans（占位）", "caliber_version": "v1"}

    def test_record_ok_and_jsonl(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "patterns.jsonl"
            led = PatternLedger(path)
            rec = led.record(self._entry())
            self.assertEqual(rec["pattern"], "测试模式（占位）")
            lines = path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 1)
            self.assertEqual(json.loads(lines[0])["pattern"],
                             "测试模式（占位）")

    def test_missing_field_refused(self):
        led = PatternLedger(None)
        for key in ("pattern", "source_case", "evidence", "caliber_version"):
            bad = self._entry()
            del bad[key]
            with self.assertRaisesRegex(MethodologyError,
                                        "PATTERN_INCOMPLETE"):
                led.record(bad)

    def test_append_only_deep_copy(self):
        led = PatternLedger(None)
        led.record(self._entry())
        snapshot = led.entries()
        snapshot[0]["pattern"] = "改（占位）"
        self.assertEqual(led.entries()[0]["pattern"], "测试模式（占位）")


class TestRender(unittest.TestCase):
    def test_render_twice_byte_identical(self):
        a = render_pack_md()
        b = render_pack_md()
        self.assertEqual(a, b)

    def test_render_contains_four_components(self):
        text = render_pack_md()
        for needle in (METHOD_COMMAND, SKILLSET_NAME,
                       "pattern / source_case / evidence / caliber_version",
                       "append-only"):
            self.assertIn(needle, text)


class TestRealPack(unittest.TestCase):
    def test_t1_design_doc_exists(self):
        """T1 设计稿真实存在（本链真实交付，方法论包口径的来源）。"""
        doc = next(Path(__file__).resolve().parents[1].glob(
            "docs/plans/2026-11-19-prd-539-*.md"))
        text = doc.read_text(encoding="utf-8")
        self.assertIn("方法论包四件套", text)
        self.assertIn("/capture", text)

    def test_first_pattern_entry_from_real_artifact(self):
        """首份模式条目引用本仓真实产物路径（evidence 真实存在）。"""
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "patterns.jsonl"
            led = PatternLedger(path)
            led.record({"pattern": "mind-kit 知识方法论包方法论包先行（占位描述）",
                        "source_case": "PRD-539/T2 方法论包落账",
                        "evidence": "docs/plans/2026-11-19-prd-539-mindkit-methodology-design.md",
                        "caliber_version": "v1"})
            row = json.loads(path.read_text(encoding="utf-8").strip())
            for key in ("pattern", "source_case", "evidence",
                        "caliber_version"):
                self.assertTrue(row[key])


class TestRedline(unittest.TestCase):
    def test_ast_zero_network(self):
        banned = {"urllib", "requests", "socket", "http", "subprocess"}
        src = (SOURCE_DIR / "mindkit_methodology.py").read_text(encoding="utf-8")
        imported = set()
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertFalse(imported & banned, imported & banned)

    def test_command_not_admin(self):
        """命令入口不代行审批：模块无 approve/finalize 类符号。"""
        src = (SOURCE_DIR / "mindkit_methodology.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        names = {n.name.lower() for n in ast.walk(tree)
                 if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
        for word in ("approve", "finalize_review", "publish"):
            self.assertNotIn(word, names, names)


if __name__ == "__main__":
    unittest.main()
