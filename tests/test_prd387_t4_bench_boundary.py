# -*- coding: utf-8 -*-
"""PRD-387/T4 测试（trend #1891 的 T4 环节）：入库知识验证台划界断言。
运行：uv run --with pytest python -m pytest tests/test_prd387_t4_bench_boundary.py -q
覆盖（T1 §0/§3，验收「划界断言通过」）：bench/gates 零导入 build-index/
build-wiki-site（下游零感知——新仓无既有闸门，本条以「验证台不触碰下游
脚本」为隔离主体）+ 借鉴词零出现（仅代码标识符扫描）+ 标准库-only 钉值+
零网络 AST+R1 拦截钉值+R3 八件套/词表封闭+R4 方法面封闭+STALE+确定性复现。
零网络；全合成占位 URL 一律 example.invalid。
"""
import ast
import sys
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

BENCH_MODULES = ["knowledge_verify_bench.py", "knowledge_verify_bench_gates.py"]


def recheck_fn(corpus):
    return [{"source_url": c.get("url")} for c in (corpus or [])]


def _imports_of(path: Path) -> set:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    return imported


def _code_names(path: Path) -> set:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
    return names


class TestModuleIsolation(unittest.TestCase):
    def test_bench_never_imports_downstream_scripts(self):
        """验证台面零触碰下游脚本（build-index/build-wiki-site——收件消费
        验证过的源，验证台零感知下游）。"""
        for mod in BENCH_MODULES:
            imported = _imports_of(SCRIPTS / mod)
            for banned in ("build-index", "build-wiki-site", "brain-server"):
                self.assertNotIn(banned, imported, f"{mod} 导入 {banned}")
            names = _code_names(SCRIPTS / mod)
            for symbol in ("build_index", "build_wiki_site"):
                self.assertNotIn(symbol, names, f"{mod} 引用 {symbol}")

    def test_upstream_zero_symbols(self):
        """借鉴仓（codex-security Apache-2.0/security-audit-skill MIT 实测）
        零符号——只借控制面形态（仅代码标识符扫描）。"""
        for mod in BENCH_MODULES:
            names = {n.lower() for n in _code_names(SCRIPTS / mod)}
            for word in ("codex", "audit_skill"):
                self.assertNotIn(word, names, f"{mod} 出现 {word}")

    def test_stdlib_only_and_redline_ast(self):
        """标准库-only 钉值：bench 静态导入全标准库（gates 只 import 同链
        corpus_fingerprint）；零网络零子进程。"""
        imported = _imports_of(SCRIPTS / "knowledge_verify_bench.py")
        self.assertLessEqual(imported - {"__future__", "copy", "hashlib",
                                         "json", "pathlib", "typing"},
                             set(), imported)
        gates_imported = _imports_of(SCRIPTS / "knowledge_verify_bench_gates.py")
        self.assertLessEqual(gates_imported - {"__future__", "typing",
                                               "knowledge_verify_bench"},
                             set())
        for mod in BENCH_MODULES:
            imported = _imports_of(SCRIPTS / mod)
            self.assertFalse(imported & {"urllib", "requests", "socket",
                                         "http", "subprocess"},
                             f"{mod} 导入网络/子进程")


class TestRedLinePins(unittest.TestCase):
    def test_r2_deterministic(self):
        """R2：同一输入 verify_knowledge 两遍逐字节一致（确定性复现）。"""
        a = verify_knowledge(ITEM, CORPUS, recheck_fn, at=NOW)
        b = verify_knowledge(ITEM, CORPUS, recheck_fn, at=NOW)
        self.assertEqual(a, b)

    def test_r1_unverified_blocked_at_outlet(self):
        """R1 拦截钉值：UNVERIFIED 不进 verified 分组（不进 Wiki）。"""
        out = verify_items([dict(ITEM, quote="不存在的引用（占位）")], CORPUS,
                           recheck_fn, at=NOW)
        self.assertEqual(out["verified"], [])
        self.assertEqual(out["unverified_count"], 1)

    def test_r3_eight_piece_closed_and_fp_family(self):
        """R3 钉值：账目缺件 BENCH_INCOMPLETE；verdict 词表封闭；语料指纹
        sha16 同族钉值（确定性）。"""
        led = KnowledgeBenchLedger(None)
        with self.assertRaisesRegex(KnowledgeBenchError, "BENCH_INCOMPLETE"):
            led.record({"schema": BENCH_SCHEMA}, at=NOW)
        self.assertEqual(set(VERDICTS), {"VERIFIED", "UNVERIFIED"})
        fp = corpus_fingerprint(CORPUS)
        self.assertTrue(fp.startswith("sha16:"))
        self.assertEqual(fp, corpus_fingerprint(CORPUS))

    def test_r4_ledger_surface_closed_and_stale(self):
        """R4：Ledger 方法面封闭（零删除方法）+reverify 语料变更 BENCH_STALE
        拒绝复用。"""
        led = KnowledgeBenchLedger(None)
        methods = {n for n in dir(led) if not n.startswith("_")}
        self.assertLessEqual(methods, {"record", "entries", "latest_for",
                                       "reverify"}, methods)
        led.record(verify_knowledge(ITEM, CORPUS, recheck_fn, at=NOW), at=NOW)
        out = led.reverify("k-001", [{"url": "https://x.example.invalid（占位）",
                                      "text": "其他（占位）"}], recheck_fn,
                           at=NOW)
        self.assertEqual(out["refused"], "BENCH_STALE")


if __name__ == "__main__":
    unittest.main()
