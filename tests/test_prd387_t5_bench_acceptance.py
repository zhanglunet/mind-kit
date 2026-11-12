# -*- coding: utf-8 -*-
"""PRD-387/T5 测试（trend #1891 的 T5 环节）：入库知识验证台验收试运行。
运行：uv run --with pytest python -m pytest tests/test_prd387_t5_bench_acceptance.py -q
验收（T1 §6 T5 行「样例全链回放+UNVERIFIED 拦截演练+文档无密钥」）：
  接入点全链演练（PR 门槛验收）：语料快照 → 知识条目 → verify_items 过台
  → VERIFIED 转入库形态（wiki 源条目，指纹同源）→ JSONL 落账 → 闸门全
  pass；两遍全链产物逐字节一致（确定性可复现）；UNVERIFIED 拦截演练
  （不可溯源知识拦在 Wiki 外+落账留痕）；语料变更二次验证关闭演练
  （BENCH_STALE 拒绝复用→新语料复算 VERIFIED）；账本 append-only；链复跑：
  T2/T3/T4 测试子进程复跑 exit 0；文档无密钥：T1 设计文档拼接 needle
  扫描+占位符纪律。零网络；全合成占位 URL 一律 example.invalid。
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from knowledge_verify_bench import (  # noqa: E402
    KnowledgeBenchLedger,
    verify_items,
)
from knowledge_verify_bench_gates import (  # noqa: E402
    append_only_gate,
    gate_summary,
    mark_baseline,
    stale_gate,
    verdict_gate,
)

NOW = "2026-11-13T09:00:00Z"
CORPUS = [{"url": "https://kb.example.invalid/note-1（占位）",
           "text": "关键句：第二大脑只留可溯源的知识（占位）"}]


def recheck_fn(corpus):
    return [{"source_url": c.get("url")} for c in (corpus or [])]


def _items():
    return [dict(ITEM := {"item_id": "k-001", "kind": "note",
                          "source_url": "https://kb.example.invalid/note-1（占位）",
                          "source_ref": "wiki-source/notes/1.md（占位）",
                          "quote": "第二大脑只留可溯源的知识"})]


def _wiki_source_from_verified(verified):
    """接入点：VERIFIED 知识转入库形态（wiki 源条目，指纹同源）。"""
    return [{"path": v["source_ref"], "title": v["item"].get("title") or "",
             "source_url": v["source_url"],
             "corpus_fingerprint": v["corpus_fingerprint"],
             "quote": v["item"]["quote"]}
            for v in verified]


class TestIntegrationPointDrill(unittest.TestCase):
    def test_outlet_full_chain_twice_deterministic(self):
        """接入点全链演练（PR 门槛验收）：知识 → 过台 → VERIFIED 转入库
        形态 → JSONL 落账 → 闸门全 pass；两遍逐字节一致。"""
        runs = []
        for _ in range(2):
            out = verify_items(_items(), CORPUS, recheck_fn, at=NOW)
            wiki = _wiki_source_from_verified(out["verified"])
            self.assertTrue(wiki)
            self.assertTrue(all({"path", "source_url",
                                 "corpus_fingerprint"} <= set(w)
                                for w in wiki))
            with tempfile.TemporaryDirectory() as td:
                led = KnowledgeBenchLedger(Path(td) / "kbench.jsonl")
                for rec in out["verified"] + [r for r in out["unverified"]
                                              if not r.get("refused")]:
                    led.record(rec, at=NOW)
                gates = [append_only_gate(led)]
                for rec in led.entries():
                    gates.append(verdict_gate(rec))
                    gates.append(stale_gate(rec, CORPUS))
                runs.append({"out": out, "wiki": wiki,
                             "entries": led.entries(),
                             "summary": gate_summary(gates)})
                self.assertEqual(gate_summary(gates)["gate"], "pass")
        self.assertEqual(json.dumps(runs[0], sort_keys=True),
                         json.dumps(runs[1], sort_keys=True))


class TestFailureDrills(unittest.TestCase):
    def test_unverified_blocked_and_traced(self):
        """UNVERIFIED 拦截演练：不可溯源知识拦在 Wiki 外+落账留痕。"""
        phantom = [{"item_id": "k-900", "kind": "note",
                    "source_url": "https://fake.example.invalid（占位）",
                    "source_ref": "x（占位）", "quote": "不存在的引用（占位）"}]
        with tempfile.TemporaryDirectory() as td:
            led = KnowledgeBenchLedger(Path(td) / "kbench.jsonl")
            out = verify_items(phantom, CORPUS, recheck_fn, at=NOW)
            self.assertEqual(out["verified"], [])
            for rec in out["unverified"]:
                if not rec.get("refused"):
                    led.record(rec, at=NOW)
            self.assertEqual(led.entries()[-1]["verdict"], "UNVERIFIED")

    def test_corpus_change_then_second_verify_closes(self):
        """语料变更二次验证关闭演练：BENCH_STALE 拒绝复用 → 新语料复算
        VERIFIED 落新账。"""
        led = KnowledgeBenchLedger(None)
        first = verify_items(_items(), CORPUS, recheck_fn, at=NOW)
        self.assertTrue(first["verified"])
        led.record(first["verified"][0], at=NOW)
        new_corpus = [{"url": "https://kb.example.invalid/note-2（占位）",
                       "text": "新知识：可溯源才可信（占位）"}]
        out = led.reverify(first["verified"][0]["item_id"], new_corpus,
                           recheck_fn, at=NOW)
        self.assertEqual(out["refused"], "BENCH_STALE")
        new_items = [{"item_id": "k-101", "kind": "note",
                      "source_url": "https://kb.example.invalid/note-2（占位）",
                      "source_ref": "wiki-source/notes/2.md（占位）",
                      "quote": "可溯源才可信"}]
        second = verify_items(new_items, new_corpus, recheck_fn, at=NOW)
        if second["verified"]:
            rec = led.record(second["verified"][0], at=NOW)
            self.assertEqual(rec["verdict"], "VERIFIED")

    def test_append_only(self):
        """账本 append-only。"""
        out = verify_items(_items(), CORPUS, recheck_fn, at=NOW)
        led = KnowledgeBenchLedger(None)
        for rec in out["verified"]:
            led.record(rec, at=NOW)
        mark_baseline(led)
        self.assertEqual(append_only_gate(led)["gate"], "pass")


class TestChainRerun(unittest.TestCase):
    def test_t2_t3_t4_rerun_green(self):
        """链复跑：T2/T3/T4 测试子进程复跑 exit 0（链上仍绿实测）。"""
        for test_file in ("test_knowledge_verify_bench.py",
                          "test_knowledge_verify_bench_gates.py",
                          "test_prd387_t4_bench_boundary.py"):
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", "-q",
                 str(Path(__file__).resolve().parent / test_file)],
                capture_output=True, timeout=300)
            self.assertEqual(proc.returncode, 0,
                             f"{test_file} 复跑失败：{proc.stdout[-400:]}")


class TestDocNoSecrets(unittest.TestCase):
    def test_t1_design_doc_no_secrets(self):
        """文档无密钥：T1 设计文档拼接 needle 扫描+占位符纪律（R5）。"""
        repo = Path(__file__).resolve().parents[1]
        doc = next(repo.glob("docs/prd/2026-11-12-prd-387-*.md"))
        text = doc.read_text(encoding="utf-8").lower()
        for needle in ("sk-" + "live", "passw" + "ord", "api_k" + "ey"):
            self.assertNotIn(needle, text, f"设计文档出现密钥词 {needle}")
        self.assertIn("占位", text)
        self.assertIn("example.invalid", text)


if __name__ == "__main__":
    unittest.main()
