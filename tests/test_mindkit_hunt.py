# -*- coding: utf-8 -*-
"""PRD-585/T2 测试（trend #2936 的 T2 环节）：mind-kit 知识产物红队巡检巡检。
运行：uv run --with pytest python -m pytest tests/test_mindkit_hunt.py -q
覆盖（T1 §2 + 红线 R1~R4）：疑点词表封闭/复现器二值返回/run_hunt 报告
结论封闭/FINDING 留痕四件缺一拒绝+repro 词表拒绝/CLI 落账/AST 零网络。
零网络；全合成占位。
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

from mindkit_hunt import (  # noqa: E402
    FINDING_REQUIRED, FindingLedger, HuntError, HUNT_CONCLUSIONS,
    REPRO_VERDICTS, SUSPECTS, main, reproduce, run_hunt)


def _artifact(poisoned=False):
    text = "正文（占位）：这是一个干净的合成产物样例。"
    if poisoned:
        text = "正文（占位）：" + "；".join(
            s.split("_", 1)[1] for s in SUSPECTS) + "。"
    return {"name": "合成产物（占位）", "text": text,
            "source_path": "samples/artifact.md（占位）"}


class TestSuspects(unittest.TestCase):
    def test_vocab_closed(self):
        self.assertEqual(len(SUSPECTS), 4)
        self.assertTrue(all(s.startswith("S") for s in SUSPECTS))

    def test_clean_no_repro(self):
        for s in SUSPECTS:
            d = reproduce(s, _artifact())
            self.assertEqual(d["verdict"], "不复现", s)

    def test_poisoned_repro(self):
        for s in SUSPECTS:
            d = reproduce(s, _artifact(poisoned=True))
            self.assertEqual(d["verdict"], "复现", s)
            self.assertIn("命中", d["evidence"])


class TestRunHunt(unittest.TestCase):
    def test_clean_conclusion(self):
        r = run_hunt(_artifact())
        self.assertEqual(r["hunt"], "无可复现发现")
        self.assertEqual(r["findings"], [])
        self.assertIn(r["hunt"], HUNT_CONCLUSIONS)

    def test_poisoned_finds_all(self):
        r = run_hunt(_artifact(poisoned=True))
        self.assertEqual(r["hunt"], "有发现")
        self.assertEqual(len(r["findings"]), len(SUSPECTS))
        for f in r["findings"]:
            for k in FINDING_REQUIRED:
                self.assertTrue(str(f.get(k, "")).strip(), k)


class TestLedger(unittest.TestCase):
    def _entry(self):
        return {"finding": "S_占位：命中（占位）", "repro": "复现",
                "evidence": "命中（占位）", "found_at": "2026-11-20T09:00:00Z"}

    def test_record_ok_and_jsonl(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "findings.jsonl"
            led = FindingLedger(path)
            rec = led.record(self._entry())
            self.assertEqual(rec["repro"], "复现")
            rows = path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(rows), 1)

    def test_missing_field_refused(self):
        led = FindingLedger(None)
        for key in FINDING_REQUIRED:
            bad = self._entry()
            del bad[key]
            with self.assertRaisesRegex(HuntError, "FINDING_INCOMPLETE"):
                led.record(bad)

    def test_no_repro_refused(self):
        """无复现证据的 finding 不入账（repro 词表外拒绝）。"""
        led = FindingLedger(None)
        bad = self._entry()
        bad["repro"] = "未复现"
        with self.assertRaisesRegex(HuntError, "REPRO_INVALID"):
            led.record(bad)

    def test_append_only_deep_copy(self):
        led = FindingLedger(None)
        led.record(self._entry())
        snapshot = led.entries()
        snapshot[0]["finding"] = "改（占位）"
        self.assertNotEqual(led.entries()[0]["finding"], "改（占位）")


class TestCLI(unittest.TestCase):
    def test_cli_produces_report(self):
        with tempfile.TemporaryDirectory() as td:
            ap = Path(td) / "artifact.md"
            ap.write_text(_artifact(poisoned=True)["text"], encoding="utf-8")
            rp = Path(td) / "report.json"
            main(["--artifact", str(ap), "--report", str(rp)])
            data = json.loads(rp.read_text(encoding="utf-8"))
            self.assertIn("hunt", data)
            self.assertIn("findings", data)


class TestRedline(unittest.TestCase):
    def test_ast_zero_network(self):
        banned = {"urllib", "requests", "socket", "http", "subprocess"}
        src = (MODULE_DIR / "mindkit_hunt.py").read_text(encoding="utf-8")
        imported = set()
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertFalse(imported & banned, imported & banned)

    def test_vocab_closed(self):
        self.assertEqual(set(REPRO_VERDICTS), {"复现", "不复现"})
        self.assertEqual(set(HUNT_CONCLUSIONS),
                         {"有发现", "无可复现发现"})
        self.assertEqual(len(FINDING_REQUIRED), 4)


if __name__ == "__main__":
    unittest.main()
