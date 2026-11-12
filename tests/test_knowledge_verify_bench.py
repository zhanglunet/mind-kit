# -*- coding: utf-8 -*-
"""PRD-387/T2 测试（trend #1891 的 T2 环节）：入库知识验证台。

运行：python3 -m pytest tests/test_knowledge_verify_bench.py -q（仓库根执行）

覆盖（T1 §4 + R1~R4）：verify_knowledge 八件套校验（缺一 BENCH_INCOMPLETE）；
来源可复访+quote 回指双 match → VERIFIED / 任一不符 → UNVERIFIED（词表
封闭）；verify_items 入库包装（UNVERIFIED 拦下）；KnowledgeBenchLedger
JSONL 真实落库+八件套缺一/词表外/REPRO_MISMATCH 声称拒绝；reverify 语料
变更二次验证（指纹不符 BENCH_STALE 拒绝复用/一致正常复验）；AST 零网络零
子进程。零网络（复访=对语料快照复算）；全合成占位 URL 一律 example.invalid。
"""
import ast
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from knowledge_verify_bench import (  # noqa: E402
    BENCH_SCHEMA,
    ERROR_CODES,
    KnowledgeBenchError,
    KnowledgeBenchLedger,
    VERDICTS,
    corpus_fingerprint,
    verify_items,
    verify_knowledge,
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


class TestVerifyKnowledge(unittest.TestCase):
    def test_verified_double_match(self):
        out = verify_knowledge(ITEM, CORPUS, recheck_fn, at=NOW)
        self.assertEqual(out["verdict"], "VERIFIED")
        self.assertEqual(out["schema"], BENCH_SCHEMA)
        fp = corpus_fingerprint(CORPUS)
        self.assertTrue(fp.startswith("sha16:"))
        self.assertEqual(out["corpus_fingerprint"], fp)

    def test_unverified_when_source_missing(self):
        out = verify_knowledge(dict(ITEM,
                                    source_url="https://x.example.invalid（占位）"),
                               CORPUS, recheck_fn, at=NOW)
        self.assertEqual(out["verdict"], "UNVERIFIED")
        self.assertFalse(out["reproduce"]["source_match"])

    def test_unverified_when_quote_missing(self):
        out = verify_knowledge(dict(ITEM, quote="不存在的引用（占位）"), CORPUS,
                               recheck_fn, at=NOW)
        self.assertEqual(out["verdict"], "UNVERIFIED")
        self.assertFalse(out["reproduce"]["quote_match"])

    def test_incomplete_refused(self):
        bad = dict(ITEM)
        del bad["quote"]
        out = verify_knowledge(bad, CORPUS, recheck_fn, at=NOW)
        self.assertEqual(out["refused"], "BENCH_INCOMPLETE")
        out2 = verify_knowledge(ITEM, CORPUS, None, at=NOW)
        self.assertEqual(out2["refused"], "BENCH_INCOMPLETE")

    def test_verdict_vocab_closed(self):
        self.assertEqual(set(VERDICTS), {"VERIFIED", "UNVERIFIED"})


class TestVerifyItems(unittest.TestCase):
    def test_outlet_blocks_unverified(self):
        """入库包装：UNVERIFIED 拦下不进 Wiki（R1）。"""
        items = [ITEM, dict(ITEM, item_id="k-002",
                            quote="不存在的引用（占位）")]
        out = verify_items(items, CORPUS, recheck_fn, at=NOW)
        self.assertEqual(len(out["verified"]), 1)
        self.assertEqual(out["unverified_count"], 1)
        self.assertEqual(out["unverified"][0]["item_id"], "k-002")


class TestKnowledgeBenchLedger(unittest.TestCase):
    def test_jsonl_persistence_append_only(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "kbench" / "ledger.jsonl"
            led = KnowledgeBenchLedger(path)
            led.record(verify_knowledge(ITEM, CORPUS, recheck_fn, at=NOW),
                       at=NOW)
            led.record(verify_knowledge(dict(ITEM, item_id="k-002"), CORPUS,
                                        recheck_fn, at=NOW), at=NOW)
            self.assertEqual(len(led.entries()), 2)
            lines = path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 2)
            self.assertEqual(json.loads(lines[0])["item_id"], "k-001")

    def test_record_refusals(self):
        led = KnowledgeBenchLedger(None)
        with self.assertRaisesRegex(KnowledgeBenchError, "BENCH_INCOMPLETE"):
            led.record({"schema": BENCH_SCHEMA}, at=NOW)
        with self.assertRaisesRegex(KnowledgeBenchError,
                                    "BENCH_REPRO_MISMATCH"):
            bad = verify_knowledge(ITEM, CORPUS, recheck_fn, at=NOW)
            bad = dict(bad, verdict="VERIFIED",
                       reproduce={"source_match": True, "quote_match": False,
                                  "detail": "改（占位）"})
            led.record(bad, at=NOW)


class TestReverify(unittest.TestCase):
    def test_stale_refuses_reuse(self):
        """语料变更 → BENCH_STALE 拒绝复用旧 VERIFIED。"""
        led = KnowledgeBenchLedger(None)
        led.record(verify_knowledge(ITEM, CORPUS, recheck_fn, at=NOW),
                   at=NOW)
        new_corpus = [{"url": "https://kb.example.invalid/note-2（占位）",
                       "text": "其他（占位）"}]
        out = led.reverify("k-001", new_corpus, recheck_fn, at=NOW)
        self.assertEqual(out["refused"], "BENCH_STALE")

    def test_same_corpus_reverify_ok(self):
        led = KnowledgeBenchLedger(None)
        led.record(verify_knowledge(ITEM, CORPUS, recheck_fn, at=NOW),
                   at=NOW)
        out = led.reverify("k-001", CORPUS, recheck_fn, at=NOW)
        self.assertEqual(out["verdict"], "VERIFIED")


class TestRedline(unittest.TestCase):
    def test_ast_zero_network_zero_subprocess(self):
        """AST：零网络零子进程（复访=对语料快照复算）。"""
        banned = {"urllib", "requests", "socket", "http", "subprocess"}
        src = SCRIPTS / "knowledge_verify_bench.py"
        tree = ast.parse(src.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertFalse(imported & banned, imported & banned)

    def test_error_codes_closed(self):
        self.assertEqual(set(ERROR_CODES),
                         {"BENCH_INCOMPLETE", "BENCH_REPRO_MISMATCH",
                          "BENCH_STALE"})


if __name__ == "__main__":
    unittest.main()
