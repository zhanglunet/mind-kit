# -*- coding: utf-8 -*-
"""PRD-562/T2 测试（trend #2659 的 T2 环节）：准入检查最小实现。
运行：python3 -m unittest discover skill/mind-kit/scripts -p "test_mindkit_admission.py"
覆盖（T1 §2 五层 + 红线）：L1 静态完整性五项/L2 安全扫描/L3 重叠检测/
L4 合成评测（带钉值）/L5 待补测诚实口径/留痕 JSONL 四件缺一拒绝/CLI/
AST 零网络。零网络；全合成占位。
"""
import ast
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SRC))
MODULE_DIR = SRC

from mindkit_admission import (  # noqa: E402
    AdmissionError, AdmissionLedger, PATTERN_REQUIRED, VERDICTS, LAYERS,
    run_admission, static_checks, security_scan, overlap_check, synth_eval,
    live_eval, main)


def _skill(name="测试技能（占位）", full=True):
    fm_lines = ["---"]
    if full:
        fm_lines += ["name: " + name, "description: 测试技能描述（占位）",
                     "触发条件：当用户需要测试（占位）", "约束：不越界（占位）",
                     "证据来源：SKILL.md（占位）"]
    fm_lines += ["---", "正文（占位）"]
    return {"name": name, "text": "\n".join(fm_lines),
            "source_path": f"skills/{name}/SKILL.md"}


class TestL1(unittest.TestCase):
    def test_full_skill_passes(self):
        checks = static_checks(_skill())
        self.assertTrue(all(checks.values()), checks)

    def test_missing_description_refused(self):
        s = _skill()
        s["text"] = s["text"].replace("description: 测试技能描述（占位）", "")
        checks = static_checks(s)
        self.assertFalse(checks["description"])


class TestL2(unittest.TestCase):
    def test_clean_passes(self):
        self.assertEqual(security_scan(_skill())["verdict"], "过")

    def test_dangerous_refused(self):
        s = _skill()
        s["text"] += "\nDROP TABLE users（占位危险）"
        d = security_scan(s)
        self.assertEqual(d["verdict"], "不过")
        self.assertTrue(d["hits"])


class TestL3(unittest.TestCase):
    def test_no_overlap_passes(self):
        # fixture 文本骨架相同导致 bigram 偏高——覆盖 text 为真正差异化内容
        existing = [_skill("旧技能Alpha"), _skill("旧技能Beta")]
        existing[0]["text"] = "name: 旧技能Alpha\ndescription: 财务报表分析中的方差分解与趋势预测（差异化正文段落甲）"
        existing[1]["text"] = "name: 旧技能Beta\ndescription: 供应链物流成本建模与库存周转优化（差异化正文段落乙）"
        d = overlap_check(_skill("新技能Omega"), existing)
        self.assertEqual(d["verdict"], "过")

    def test_identical_suspect(self):
        d = overlap_check(_skill("技能"), [_skill("技能")])
        self.assertEqual(d["verdict"], "疑似")
        self.assertTrue(d["suspects"])


class TestL4L5(unittest.TestCase):
    def test_synth_with_pin(self):
        d = synth_eval(_skill())
        self.assertEqual(d["verdict"], "过")
        self.assertTrue(d["questions"])

    def test_live_pending(self):
        """无对照数据判待补测（不编造结论）。"""
        d = live_eval(_skill())
        self.assertEqual(d["verdict"], "待补测")


class TestLedger(unittest.TestCase):
    def _entry(self):
        return {"layer": "L1_quality", "verdict": "过",
                "evidence": "全项过（占位）",
                "checked_at": "2026-11-20T09:00:00Z"}

    def test_record_ok_and_jsonl(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "admission.jsonl"
            led = AdmissionLedger(path)
            rec = led.record(self._entry())
            self.assertEqual(rec["layer"], "L1_quality")
            rows = path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(rows), 1)

    def test_missing_field_refused(self):
        led = AdmissionLedger(None)
        for key in PATTERN_REQUIRED:
            bad = self._entry()
            del bad[key]
            with self.assertRaisesRegex(AdmissionError, "ENTRY_INCOMPLETE"):
                led.record(bad)

    def test_append_only_deep_copy(self):
        led = AdmissionLedger(None)
        led.record(self._entry())
        snapshot = led.entries()
        snapshot[0]["verdict"] = "改（占位）"
        self.assertEqual(led.entries()[0]["verdict"], "过")


class TestCLI(unittest.TestCase):
    def test_cli_produces_report(self):
        with tempfile.TemporaryDirectory() as td:
            skill_path = Path(td) / "SKILL.md"
            skill_path.write_text(_skill(full=True)["text"], encoding="utf-8")
            report_path = Path(td) / "report.json"
            main(["--skill", str(skill_path), "--report", str(report_path)])
            data = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertIn("admission", data)


class TestRedline(unittest.TestCase):
    def test_ast_zero_network(self):
        banned = {"urllib", "requests", "socket", "http", "subprocess"}
        src = (MODULE_DIR / "mindkit_admission.py").read_text(encoding="utf-8")
        imported = set()
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertFalse(imported & banned, imported & banned)

    def test_vocab_closed(self):
        self.assertEqual(len(LAYERS), 5)
        self.assertEqual(set(VERDICTS), {"过", "不过", "疑似", "待补测"})
        self.assertEqual(len(PATTERN_REQUIRED), 4)


if __name__ == "__main__":
    unittest.main()
