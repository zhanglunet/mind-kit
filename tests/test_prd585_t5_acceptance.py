# -*- coding: utf-8 -*-
"""PRD-585/T5 测试（trend #2939 的 T5 环节）：mind-kit 知识产物红队巡检验收试运行。
运行：uv run --with pytest python -m pytest tests/test_prd585_t5_acceptance.py -q
验收（PRD 任务拆分 T5 行）：真实产物按巡检走一遍，结论可复核——
  - 合成产物全疑点跑通 + FINDING 留痕过闸（append-only+复现证据+
    误报复核+结论词表封闭）；
  - 两遍巡检结论一致（可复核）；
  - 链复跑 T2/T3/T4 子进程 exit 0；
  - T1 设计文档无密钥（拼接 needle）。
零网络；真实文件只读 + 合成占位。
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

MOD_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(MOD_DIR))
MODULE_DIR = MOD_DIR

from mindkit_hunt import (  # noqa: E402
    FINDING_REQUIRED, FindingLedger, SUSPECTS, main, run_hunt)
from mindkit_hunt_gate import (  # noqa: E402
    append_only_gate, check_fp_veto, check_hunt_vocab, check_repro_evidence,
    gate_summary)


def _poisoned_text():
    return "正文（占位）：" + "；".join(
        s.split("_", 1)[1] for s in SUSPECTS) + "。"


class TestRealRun(unittest.TestCase):
    def test_hunt_twice_identical(self):
        a = run_hunt({"name": "合成产物（占位）", "text": _poisoned_text(),
                      "source_path": "samples（占位）"})
        b = run_hunt({"name": "合成产物（占位）", "text": _poisoned_text(),
                      "source_path": "samples（占位）"})
        self.assertEqual(a["hunt"], b["hunt"])
        self.assertEqual(len(a["findings"]), len(SUSPECTS))

    def test_cli_real_run(self):
        with tempfile.TemporaryDirectory() as td:
            ap = Path(td) / "artifact.md"
            ap.write_text(_poisoned_text(), encoding="utf-8")
            rp = Path(td) / "report.json"
            main(["--artifact", str(ap), "--report", str(rp)])
            data = json.loads(rp.read_text(encoding="utf-8"))
            self.assertEqual(data["hunt"], "有发现")


class TestGates(unittest.TestCase):
    def test_findings_pass_all_gates(self):
        r = run_hunt({"name": "合成产物（占位）", "text": _poisoned_text(),
                      "source_path": "samples（占位）"})
        with tempfile.TemporaryDirectory() as td:
            led = FindingLedger(Path(td) / "findings.jsonl")
            entries = [led.record(f) for f in r["findings"]]
            for f in entries:
                for k in FINDING_REQUIRED:
                    self.assertTrue(str(f.get(k, "")).strip(), k)
            checks = [append_only_gate(entries, entries[0], len(entries)),
                      check_repro_evidence(entries),
                      check_fp_veto(entries),
                      check_hunt_vocab(r["hunt"])]
            s = gate_summary(checks)
            self.assertEqual(s["gate"], "pass", json.dumps(s["reasons"]))

    def test_no_repro_not_admitted(self):
        """红线 R1：无复现证据的 finding 不入账（闸门拦下）。"""
        bad = {"finding": "占位", "repro": "未复现", "evidence": "",
               "found_at": "2026-11-20T09:00:00Z"}
        d = check_repro_evidence([bad])
        self.assertEqual(d["gate"], "block")


class TestChainRerun(unittest.TestCase):
    def test_t2_t3_t4_rerun_green(self):
        for name in ("test_mindkit_hunt.py", "test_mindkit_hunt_gate.py", "test_prd585_t4_boundary.py"):
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", "-q",
                 str(Path(__file__).resolve().parent / name)],
                capture_output=True, timeout=600)
            self.assertEqual(proc.returncode, 0,
                             f"{name} 复跑失败："
                             f"{(proc.stdout or proc.stderr or '')[-400:]}")


class TestDocNoSecrets(unittest.TestCase):
    def test_t1_design_doc_no_secrets(self):
        doc = next(Path(__file__).resolve().parents[1].glob(
            "docs/plans/2026-11-20-prd-585-*-hunting-design.md"))
        text = doc.read_text(encoding="utf-8").lower()
        for needle in ("sk-" + "live", "passw" + "ord =",
                       "begin private", "akia" + "x"):
            self.assertNotIn(needle, text, f"设计文档出现密钥样式 {needle}")
        self.assertIn("巡检", text)


if __name__ == "__main__":
    unittest.main()
