# -*- coding: utf-8 -*-
"""PRD-387/T3 测试（trend #1891 的 T3 环节）：入库知识验证台闸门。
运行：uv run --with pytest python -m pytest tests/test_knowledge_verify_bench_gates.py -q
覆盖（T1 §5 + R1/R3/R4）：append_only_gate 四形态+verdict_gate 双向对账+
stale_gate+gate_summary 一票否决+与 T2 串联+ERROR_CODES 随模块导出+
AST 零网络+闸门只读。零网络；全合成占位。
"""
import ast
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from knowledge_verify_bench import KnowledgeBenchLedger, verify_knowledge  # noqa: E402
from knowledge_verify_bench_gates import (  # noqa: E402
    ERROR_CODES,
    append_only_gate,
    gate_summary,
    mark_baseline,
    stale_gate,
    verdict_gate,
)

NOW = "2026-11-13T09:00:00Z"
CORPUS = [{"url": "https://kb.example.invalid/note-1（占位）",
           "text": "关键句：第二大脑只留可溯源的知识（占位）"}]
ITEM = {"item_id": "k-001", "kind": "note",
        "source_url": "https://kb.example.invalid/note-1（占位）",
        "source_ref": "wiki-source/notes/1.md（占位）",
        "quote": "第二大脑只留可溯源的知识"}


def recheck_fn(corpus):
    return [{"source_url": c.get("url")} for c in (corpus or [])]


def _ledger():
    led = KnowledgeBenchLedger(None)
    led.record(verify_knowledge(ITEM, CORPUS, recheck_fn, at=NOW), at=NOW)
    led.record(verify_knowledge(dict(ITEM, item_id="k-002"), CORPUS,
                                recheck_fn, at=NOW), at=NOW)
    return led


class TestAppendOnlyGate(unittest.TestCase):
    def test_no_baseline_form_check_passes(self):
        self.assertEqual(append_only_gate(_ledger())["gate"], "pass")

    def test_mark_baseline_then_append_passes(self):
        led = _ledger()
        mark_baseline(led)
        led.record(verify_knowledge(dict(ITEM, item_id="k-003"), CORPUS,
                                    recheck_fn, at=NOW), at=NOW)
        self.assertEqual(append_only_gate(led)["gate"], "pass")

    def test_deletion_detected(self):
        led = _ledger()
        mark_baseline(led)
        led._records.pop()
        self.assertEqual(append_only_gate(led)["gate"], "LEDGER_DRIFT")

    def test_first_record_rewrite_detected(self):
        led = _ledger()
        mark_baseline(led)
        led._records[0]["verdict"] = "UNVERIFIED"
        self.assertEqual(append_only_gate(led)["gate"], "LEDGER_DRIFT")

    def test_non_ledger_object_visible(self):
        self.assertEqual(append_only_gate(object())["gate"], "LEDGER_DRIFT")


class TestVerdictGate(unittest.TestCase):
    def test_consistent_record_passes(self):
        rec = verify_knowledge(ITEM, CORPUS, recheck_fn, at=NOW)
        self.assertEqual(verdict_gate(rec)["gate"], "pass")

    def test_verified_but_partial_mismatch(self):
        rec = verify_knowledge(ITEM, CORPUS, recheck_fn, at=NOW)
        rec["reproduce"]["quote_match"] = False
        self.assertEqual(verdict_gate(rec)["gate"], "BENCH_REPRO_MISMATCH")

    def test_unverified_but_double_match_mismatch(self):
        rec = verify_knowledge(ITEM, CORPUS, recheck_fn, at=NOW)
        rec["verdict"] = "UNVERIFIED"   # 词表内但与双 match 不一致
        self.assertEqual(verdict_gate(rec)["gate"], "BENCH_REPRO_MISMATCH")

    def test_vocab_out_and_missing_visible(self):
        rec = dict(verify_knowledge(ITEM, CORPUS, recheck_fn, at=NOW),
                   verdict="MAYBE（占位）")
        self.assertEqual(verdict_gate(rec)["gate"], "BENCH_INCOMPLETE")
        out = verdict_gate({"item_id": "x"})
        self.assertEqual(out["gate"], "BENCH_INCOMPLETE")
        self.assertTrue(any("缺" in r for r in out["reasons"]))


class TestStaleGate(unittest.TestCase):
    def test_matching_fingerprint_passes(self):
        rec = verify_knowledge(ITEM, CORPUS, recheck_fn, at=NOW)
        self.assertEqual(stale_gate(rec, CORPUS)["gate"], "pass")

    def test_stale_fingerprint_visible(self):
        rec = verify_knowledge(ITEM, CORPUS, recheck_fn, at=NOW)
        out = stale_gate(rec, [{"url": "https://kb.example.invalid/note-2（占位）",
                                "text": "其他（占位）"}])
        self.assertEqual(out["gate"], "BENCH_STALE")


class TestSummaryAndChain(unittest.TestCase):
    def test_summary_one_block_votes_all(self):
        led = _ledger()
        led.record(verify_knowledge(dict(ITEM, item_id="k-003"), CORPUS,
                                    recheck_fn, at=NOW), at=NOW)
        rec = verify_knowledge(ITEM, CORPUS, recheck_fn, at=NOW)
        rec["reproduce"]["quote_match"] = False
        out = gate_summary([append_only_gate(led), verdict_gate(rec)])
        self.assertEqual(out["gate"], "block")
        self.assertEqual(out["gates_checked"], 2)

    def test_chain_with_real_t2_products(self):
        led = _ledger()
        mark_baseline(led)
        rec = verify_knowledge(ITEM, CORPUS, recheck_fn, at=NOW)
        results = [append_only_gate(led), verdict_gate(rec),
                   stale_gate(rec, CORPUS)]
        self.assertTrue(all(r["gate"] == "pass" for r in results))
        self.assertEqual(gate_summary(results)["gate"], "pass")

    def test_error_codes_closed_and_exported(self):
        import knowledge_verify_bench_gates as g
        self.assertEqual(set(g.ERROR_CODES),
                         {"LEDGER_DRIFT", "BENCH_INCOMPLETE",
                          "BENCH_REPRO_MISMATCH", "BENCH_STALE"})


class TestRedline(unittest.TestCase):
    def test_ast_zero_network_readonly(self):
        banned = {"urllib", "requests", "socket", "http", "subprocess"}
        src = SCRIPTS / "knowledge_verify_bench_gates.py"
        tree = ast.parse(src.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertFalse(imported & banned, imported & banned)
        text = src.read_text(encoding="utf-8")
        for call in (".record(", ".append("):
            self.assertNotIn(call, text, f"闸门出现账本写调用 {call}")


if __name__ == "__main__":
    unittest.main()
