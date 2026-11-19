# -*- coding: utf-8 -*-
"""PRD-562/T5 测试（trend #2662 的 T5 环节）：准入检查验收试运行。
运行：python3 -m unittest discover skill/mind-kit/scripts -p "test_prd562_t5_acceptance.py"
验收（PRD 任务拆分 T5 行）：真实技能按准入检查走一遍，结论可复核——
  - 真实 SKILL.md 五层跑通 + 两遍逐字节一致；
  - 闸门全链（留痕 append-only+五层覆盖+一票否决+词表封闭）全 pass；
  - 链复跑 T2/T3/T4 子进程 exit 0；
  - T1 设计文档无密钥。零网络；全合成占位。
"""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parent
sys.path.insert(0, str(SRC))
MODULE_DIR = SRC

from mindkit_admission import (  # noqa: E402
    AdmissionLedger, run_admission)
from mindkit_admission_gate import (  # noqa: E402
    append_only_gate, check_layer_coverage, check_one_vote,
    check_no_auto_admit, gate_summary)

NOW = "2026-11-20T09:00:00Z"


def _skill(name="测试技能（占位）", desc="差异化描述（占位正文段落）"):
    return {"name": name,
            "text": f"name: {name}\ndescription: {desc}",
            "source_path": f"skills/{name}/SKILL.md"}


class TestFullRun(unittest.TestCase):
    def test_real_run_twice_identical(self):
        """真实技能五层跑两遍逐字节一致。"""
        with tempfile.TemporaryDirectory() as td:
            skill_path = Path(td) / "SKILL.md"
            skill_path.write_text(_skill()["text"], encoding="utf-8")
            skill = {"name": "test-skill（占位）",
                     "text": skill_path.read_text(encoding="utf-8"),
                     "source_path": str(skill_path)}
            r1 = run_admission(skill, [])
            r2 = run_admission(skill, [])
            a = json.dumps(r1, sort_keys=True, ensure_ascii=False)
            b = json.dumps(r2, sort_keys=True, ensure_ascii=False)
            self.assertEqual(a, b)

    def test_ledger_five_layers(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "admission.jsonl"
            led = AdmissionLedger(path)
            for layer in ("L1_quality", "L2_security", "L3_overlap",
                          "L4_synth", "L5_live"):
                led.record({"layer": layer, "verdict": "过",
                            "evidence": "占位", "checked_at": NOW})
            rows = path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(rows), 5)


class TestGateChain(unittest.TestCase):
    def test_full_gate_chain_pass(self):
        """闸门全链：留痕+覆盖+一票否决+词表封闭 全 pass。"""
        led = make_ledger(5)
        entries = led.entries()
        checks = [
            append_only_gate(entries, entries[0], len(entries)),
            check_layer_coverage(entries),
            check_one_vote(entries, "可进收件箱"),
            check_no_auto_admit("可进收件箱"),
        ]
        self.assertEqual(gate_summary(checks)["gate"], "pass")


def make_ledger(n=5):
    led = AdmissionLedger(None)
    layers = ("L1_quality", "L2_security", "L3_overlap", "L4_synth", "L5_live")
    for i in range(n):
        led.record({"layer": layers[i % len(layers)], "verdict": "过",
                    "evidence": f"占位 {i}", "checked_at": NOW})
    return led


class TestChainRerun(unittest.TestCase):
    def test_t2_t3_t4_rerun_green(self):
        for name in ("test_mindkit_admission.py",
                     "test_mindkit_admission_gate.py",
                     "test_prd562_t4_boundary.py"):
            proc = subprocess.run(
                [sys.executable, "-m", "unittest", "discover",
                 "skill/mind-kit/scripts", "-p", name],
                capture_output=True, timeout=600)
            self.assertEqual(proc.returncode, 0, f"{name} 复跑失败")


class TestDocNoSecrets(unittest.TestCase):
    def test_t1_design_doc_no_secrets(self):
        doc = next(Path(__file__).resolve().parents[3].glob(
            "docs/plans/2026-11-20-prd-562-*.md"))
        text = doc.read_text(encoding="utf-8").lower()
        for needle in ("sk-" + "live", "passw" + "ord =",
                       "begin private", "akia" + "x"):
            self.assertNotIn(needle, text, f"设计文档出现密钥样式 {needle}")
        self.assertIn("准入检查", text)


if __name__ == "__main__":
    unittest.main()
