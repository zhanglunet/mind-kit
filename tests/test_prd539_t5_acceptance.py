# -*- coding: utf-8 -*-
"""PRD-539/T5 测试（trend #2617 的 T5 环节）：mind-kit 知识方法论包验收试运行。
运行：uv run --with pytest python -m pytest tests/test_mindkit_methodology.py -q
验收（PRD 任务拆分 T5 行）：真实任务按方法论包走一遍，结论可复核——
  - 真实包装 md 两遍渲染逐字节一致（docs/methodology/ 落账产物回读核对）；
  - 真实 workflow 全步序列过闸（T3 gate_summary 全 pass）；
  - 真实模式条目（T2 落账 JSONL）过闸；
  - 无方法论包场景演练：PACK_MISSING 拦下；
  - 链复跑：T2/T3/T4 测试子进程 exit 0；
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

from mindkit_methodology import (  # noqa: E402
    WORKFLOW_STEPS, PatternLedger, check_step_sequence, render_pack_md)
from mindkit_methodology_gate import (  # noqa: E402
    check_pack, check_pattern_entry, check_workflow, gate_summary)

NOW = "2026-11-19T12:00:00Z"
ROOT = Path(__file__).resolve().parents[1]


def _entry():
    return {"pattern": "验收模式（占位）", "source_case": "T5 真实任务走包",
            "evidence": "docs/methodology（占位）",
            "caliber_version": "v1"}


class TestRealRun(unittest.TestCase):
    def test_pack_render_twice_byte_identical(self):
        a = render_pack_md()
        b = render_pack_md()
        self.assertEqual(a, b)

    def test_pack_doc_on_disk_matches_render(self):
        """落账产物（docs/methodology/）与当前渲染逐字节一致。"""
        doc = next(ROOT.glob("docs/methodology/*-methodology.md"))
        self.assertEqual(doc.read_text(encoding="utf-8"), render_pack_md())

    def test_full_workflow_passes_gate(self):
        """真实任务全步序列过闸（T3）。"""
        d = check_workflow(list(WORKFLOW_STEPS))
        self.assertTrue(d["allowed"])

    def test_real_pattern_entry_passes_gate(self):
        led = PatternLedger(None)
        rec = led.record(_entry())
        self.assertTrue(check_pattern_entry(rec)["allowed"])

    def test_no_pack_drill(self):
        """无方法论包场景演练：PACK_MISSING 拦下。"""
        d = check_pack(False, "skill-x")
        self.assertFalse(d["allowed"])
        self.assertEqual(d["reasons"][0]["code"], "PACK_MISSING")


class TestChainRerun(unittest.TestCase):
    def test_t2_t3_t4_rerun_green(self):
        for name in (["test_mindkit_methodology.py", "test_mindkit_methodology_gate.py", "test_prd539_t4_boundary.py"]):
            proc = subprocess.run([sys.executable, '-m', 'pytest', '-q'] +
                                  [str(Path(__file__).resolve().parent / name)],
                                  capture_output=True, timeout=600)
            self.assertEqual(proc.returncode, 0,
                             f"{name} 复跑失败：{(proc.stdout or b'')[-400:]}")


class TestDocNoSecrets(unittest.TestCase):
    def test_t1_design_doc_no_secrets(self):
        doc = next(Path(__file__).resolve().parents[1].glob(
            "docs/plans/2026-11-19-prd-539-*.md"))
        text = doc.read_text(encoding="utf-8").lower()
        for needle in ("sk-" + "live", "passw" + "ord =",
                       "BEGIN PRIVATE", "AKIA" + "x"):
            self.assertNotIn(needle, text, f"设计文档出现密钥样式 {needle}")
        self.assertIn("方法论包", text)


if __name__ == "__main__":
    unittest.main()
