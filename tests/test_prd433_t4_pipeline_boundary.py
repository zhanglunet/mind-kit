# -*- coding: utf-8 -*-
"""PRD-433/T4 测试（trend #2085 的 T4 环节）：知识条目评审流水线 划界断言。
运行：uv run --with pytest python -m pytest tests/test_knowledge_review_pipeline.py -q
覆盖（T1 §0/§3）：流水线面零触碰下游载体（knowledge_verify_bench、wiki、store、knowledge_collab_session 零导入）+借鉴词零出现
（仅代码标识符扫描）+标准库-only 钉值+零网络 AST+R1 出口拦截钉值+R2 规则
先行钉值（judge_fn 未注入/未全判拒绝）+R3 账本方法面封闭+append-only+
R4 双向对账钉值。零网络；全合成占位。
"""
import ast
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
MOD_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from knowledge_review_pipeline import (  # noqa: E402
    ERROR_CODES, JUDGE_VERDICTS, RULE_IDS, VERDICTS, PipelineError,
    ReviewPipelineLedger, run_pipeline, scan_candidates)

NOW = "2026-11-14T11:00:00Z"
DRAFT = {"draft_id": "d-001", "references": ["R1"], "lines": [
    {"no": 1, "kind": "number", "text": "指标=42（占位）",
     "num": {"stated": 42, "recomputed": 41}},
    {"no": 2, "kind": "text", "text": "本段沿用旧口径（占位）表述"},
    {"no": 3, "kind": "reference", "text": "见 [ref:R1]（占位）与 [ref:R9]（占位）"},
]}
PIPELINE_MODULES = ["knowledge_review_pipeline.py", "knowledge_review_pipeline_gates.py"]


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


def judge_all_confirm(candidates):
    return [dict(c, verdict="confirmed", note="确认（占位）")
            for c in candidates]


class TestModuleIsolation(unittest.TestCase):
    def test_pipeline_never_imports_downstream_carriers(self):
        """流水线面零触碰下游载体（knowledge_verify_bench、wiki、store、knowledge_collab_session 零导入——被消费面只可上行不可下行）。"""
        for mod in PIPELINE_MODULES:
            imported = _imports_of(MOD_DIR / mod)
            for banned in ["knowledge_verify_bench", "wiki", "store", "knowledge_collab_session"]:
                self.assertNotIn(banned, imported, f"{mod} 导入 {banned}")

    def test_upstream_zero_symbols(self):
        """借鉴仓（open-code-review/elephant-goldfish Apache-2.0 实测）零符号
        ——只借双轨形态（仅代码标识符扫描，docstring 提及不算）。"""
        for mod in PIPELINE_MODULES:
            names = {n.lower() for n in _code_names(MOD_DIR / mod)}
            for word in ("open_code_review", "elephant_goldfish", "goldfish"):
                self.assertNotIn(word, names, f"{mod} 出现 {word}")

    def test_stdlib_only_and_redline_ast(self):
        """标准库-only 钉值：pipeline 静态导入全标准库；零网络零子进程。"""
        imported = _imports_of(MOD_DIR / "knowledge_review_pipeline.py")
        self.assertLessEqual(imported - {"__future__", "copy", "json", "re",
                                         "pathlib", "typing", "collections"},
                             set(), imported)
        for mod in PIPELINE_MODULES:
            imported = _imports_of(MOD_DIR / mod)
            self.assertFalse(imported & {"urllib", "requests", "socket",
                                         "http", "subprocess"},
                             f"{mod} 导入网络/子进程")


class TestRedLinePins(unittest.TestCase):
    def test_r1_blocked_blocked_at_outlet(self):
        """R1 拦截钉值：blocked 不进出口 passed。"""
        led = ReviewPipelineLedger(None)
        led.record(run_pipeline(DRAFT, judge_all_confirm, at=NOW))
        out = led.outlet([DRAFT])
        self.assertEqual(out["passed"], [])
        self.assertEqual(out["blocked_count"], 1)

    def test_r2_rules_first_pins(self):
        """R2：规则先行可复算（确定性两遍一致）+judge 未注入/未全判拒绝。"""
        self.assertEqual(scan_candidates(DRAFT), scan_candidates(DRAFT))
        out = run_pipeline(DRAFT, None, at=NOW)
        self.assertEqual(out["refused"], "REVIEW_INCOMPLETE")
        self.assertEqual(set(RULE_IDS),
                         {"R-NUM-RECALC", "R-TERM-DRIFT", "R-REF-MISSING"})

    def test_r3_surface_closed_and_append_only(self):
        """R3：Ledger 方法面封闭（零删除方法）+append-only。"""
        led = ReviewPipelineLedger(None)
        methods = {n for n in dir(led) if not n.startswith("_")}
        self.assertLessEqual(methods, {"record", "entries", "latest_for",
                                       "outlet"}, methods)
        led.record(run_pipeline(DRAFT, judge_all_confirm, at=NOW))
        mark_len = len(led.entries())
        led.record(run_pipeline(dict(DRAFT, draft_id="d-002"),
                                judge_all_confirm, at=NOW))
        self.assertEqual(len(led.entries()), mark_len + 1)

    def test_r4_verdict_bidirectional_pin(self):
        """R4：blocked⇔confirmed 双向对账+词表封闭。"""
        led = ReviewPipelineLedger(None)
        out = run_pipeline(DRAFT, judge_all_confirm, at=NOW)
        bad = dict(out, verdict="pass")
        with self.assertRaisesRegex(PipelineError, "REVIEW_VERDICT_MISMATCH"):
            led.record(bad)
        self.assertEqual(set(VERDICTS), {"pass", "blocked"})
        self.assertEqual(set(JUDGE_VERDICTS), {"confirmed", "false_positive"})
        self.assertEqual(set(ERROR_CODES),
                         {"REVIEW_INCOMPLETE", "REVIEW_VERDICT_MISMATCH"})


if __name__ == "__main__":
    unittest.main()
