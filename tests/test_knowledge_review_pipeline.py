# -*- coding: utf-8 -*-
"""PRD-433/T2 测试（trend #2085 的 T2 环节）：知识条目评审流水线。
运行：uv run --with pytest python -m pytest tests/test_knowledge_review_pipeline.py -q
覆盖（T1 §4 + R1~R4）：三条确定性规则各自命中/judge_fn 注入双向/未全判
拒绝/outlet 拦截/JSONL 落库/词表封闭/AST 零网络。零网络；全合成占位。
"""
import ast
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
MOD_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from knowledge_review_pipeline import (  # noqa: E402
    ERROR_CODES, JUDGE_VERDICTS, RULE_IDS, VERDICTS, PipelineError,
    ReviewPipelineLedger, run_pipeline, scan_candidates,
)

NOW = "2026-11-14T09:00:00Z"
DRAFT = {"draft_id": "d-001", "references": ["R1"], "lines": [
    {"no": 1, "kind": "number", "text": "指标=42（占位）",
     "num": {"stated": 42, "recomputed": 41}},
    {"no": 2, "kind": "text", "text": "本段沿用旧口径（占位）表述"},
    {"no": 3, "kind": "reference", "text": "见 [ref:R1]（占位）与 [ref:R9]（占位）"},
]}


def judge_all_confirm(candidates):
    return [dict(c, verdict="confirmed", note="确认（占位）")
            for c in candidates]


def judge_all_reject(candidates):
    return [dict(c, verdict="false_positive", note="误报（占位）")
            for c in candidates]


class TestRules(unittest.TestCase):
    def test_three_rules_hit(self):
        cands = scan_candidates(DRAFT)
        rules = {c["rule_id"] for c in cands}
        self.assertEqual(rules, set(RULE_IDS))
        self.assertTrue(all("line" in c for c in cands))

    def test_clean_draft_no_candidates(self):
        clean = {"draft_id": "d-ok", "references": ["R1"], "lines": [
            {"no": 1, "kind": "number", "text": "指标=41（占位）",
             "num": {"stated": 41, "recomputed": 41}},
            {"no": 2, "kind": "reference", "text": "见 [ref:R1]（占位）"}]}
        self.assertEqual(scan_candidates(clean), [])


class TestPipeline(unittest.TestCase):
    def test_confirmed_blocks(self):
        out = run_pipeline(DRAFT, judge_all_confirm, at=NOW)
        self.assertEqual(out["verdict"], "blocked")
        self.assertEqual(out["confirmed_count"], len(out["candidates"]))

    def test_all_false_positive_passes(self):
        out = run_pipeline(DRAFT, judge_all_reject, at=NOW)
        self.assertEqual(out["verdict"], "pass")

    def test_partial_judgment_refused(self):
        def judge_half(cands):
            return [dict(cands[0], verdict="confirmed", note="n")]
        out = run_pipeline(DRAFT, judge_half, at=NOW)
        self.assertEqual(out["refused"], "REVIEW_INCOMPLETE")

    def test_no_judge_fn_refused(self):
        out = run_pipeline(DRAFT, None, at=NOW)
        self.assertEqual(out["refused"], "REVIEW_INCOMPLETE")

    def test_unknown_candidate_refused(self):
        def judge_extra(cands):
            return judge_all_confirm(cands) + [
                {"rule_id": "R-GHOST", "line": 99, "verdict": "confirmed",
                 "note": "n"}]
        out = run_pipeline(DRAFT, judge_extra, at=NOW)
        self.assertEqual(out["refused"], "REVIEW_INCOMPLETE")

    def test_vocabs_closed(self):
        self.assertEqual(set(VERDICTS), {"pass", "blocked"})
        self.assertEqual(set(JUDGE_VERDICTS), {"confirmed", "false_positive"})


class TestLedgerOutlet(unittest.TestCase):
    def test_jsonl_persistence_append_only(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "review" / "log.jsonl"
            led = ReviewPipelineLedger(path)
            led.record(run_pipeline(DRAFT, judge_all_confirm, at=NOW))
            led.record(run_pipeline(dict(DRAFT, draft_id="d-002"),
                                    judge_all_reject, at=NOW))
            self.assertEqual(len(led.entries()), 2)
            lines = path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 2)

    def test_verdict_mismatch_refused(self):
        led = ReviewPipelineLedger(None)
        out = run_pipeline(DRAFT, judge_all_confirm, at=NOW)
        bad = dict(out, verdict="pass")
        with self.assertRaisesRegex(PipelineError, "REVIEW_VERDICT_MISMATCH"):
            led.record(bad)

    def test_outlet_blocks_blocked_draft(self):
        led = ReviewPipelineLedger(None)
        led.record(run_pipeline(DRAFT, judge_all_confirm, at=NOW))
        led.record(run_pipeline(dict(DRAFT, draft_id="d-002"),
                                judge_all_reject, at=NOW))
        out = led.outlet([DRAFT, dict(DRAFT, draft_id="d-002")])
        self.assertEqual([d["draft_id"] for d in out["passed"]], ["d-002"])
        self.assertEqual(out["blocked_count"], 1)
        self.assertEqual(out["blocked"][0]["verdict"], "blocked")


class TestRedline(unittest.TestCase):
    def test_ast_zero_network_zero_subprocess(self):
        banned = {"urllib", "requests", "socket", "http", "subprocess"}
        src = MOD_DIR / "knowledge_review_pipeline.py"
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
                         {"REVIEW_INCOMPLETE", "REVIEW_VERDICT_MISMATCH"})


if __name__ == "__main__":
    unittest.main()
