
"""PRD-585/T4 测试（trend #2938 的 T4 环节）：巡检划界断言。
运行：uv run --with pytest python -m pytest tests/test_prd585_t4_boundary.py -q
按 PRD 任务拆分 T4 行：巡检与方法论包/准入检查/契约/评估/评审流水线/
监督回路的边界断言；巡检只找问题不修问题、零自动执行。
覆盖：借鉴仓（superpowers/bughunter/opensre）零符号+只找不修钉值+
零自动执行钉值+误报一票否决钉值+词表封闭+AST 零网络零子进程。
零网络；全合成占位。
"""
import ast
import sys
import unittest
from pathlib import Path

MOD_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(MOD_DIR))
MODULE_DIR = MOD_DIR

GATEWAY = MODULE_DIR / "mindkit_hunt.py"
GATE = MODULE_DIR / "mindkit_hunt_gate.py"

from mindkit_hunt import FindingLedger, HUNT_CONCLUSIONS, REPRO_VERDICTS  # noqa: E402
from mindkit_hunt_gate import (  # noqa: E402
    ERROR_CODES, check_fp_veto, check_hunt_vocab, check_repro_evidence)

BORROWED = ("superpowers", "bughunter", "opensre")
NEIGHBOR = ("methodology", "admission", "admission_check_placeholder",
            "evaluation", "review_pipeline", "supervision")
NO_FIX_SYMBOLS = ("fix_", "repair", "apply_fix", "patch_", "approve",
                  "execute", "auto_run")


def _names_of(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.ClassDef)):
            out.add(n.name.lower())
        elif isinstance(n, ast.Name):
            out.add(n.id.lower())
    return out


class TestBorrowed(unittest.TestCase):
    def test_borrowed_zero_symbols(self):
        """借鉴仓（superpowers/bughunter/opensre）零符号。"""
        for f in (GATEWAY, GATE):
            names = _names_of(f)
            for word in BORROWED:
                self.assertNotIn(word, names, f"{f.name} 出现 {word}")


class TestNeighbor(unittest.TestCase):
    def test_neighbor_zero_imports(self):
        """邻居模块（方法论/准入/评估/评审/监督）零导入。"""
        for f in (GATEWAY, GATE):
            src = f.read_text(encoding="utf-8")
            imported = set()
            for node in ast.walk(ast.parse(src)):
                if isinstance(node, ast.Import):
                    imported.update(a.name.split(".")[0] for a in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module.split(".")[0])
            for stem in NEIGHBOR:
                self.assertFalse(
                    any(i.startswith(stem) for i in imported),
                    f"{f.name} 导入邻居 {stem}：{imported}")


class TestNoFix(unittest.TestCase):
    def test_no_fix_symbols(self):
        """巡检只找问题不修问题：无 fix/repair/approve 符号。"""
        for f in (GATEWAY, GATE):
            names = _names_of(f)
            for word in NO_FIX_SYMBOLS:
                hit = [n for n in names if word in n]
                self.assertFalse(hit, f"{f.name} 出现 {word}: {hit}")


class TestPins(unittest.TestCase):
    def test_fp_veto_pin(self):
        d = check_fp_veto([{"finding": "占位", "repro": "复现",
                            "evidence": "占位",
                            "found_at": "2026-11-20T09:00:00Z",
                            "review": "误报"}])
        self.assertEqual(d["gate"], "block")
        self.assertEqual(d["reasons"][0]["code"], "FP_ADMIT")

    def test_repro_missing_pin(self):
        d = check_repro_evidence([{"finding": "占位", "repro": "未复现",
                                   "evidence": "", "found_at": "占位"}])
        self.assertEqual(d["reasons"][0]["code"], "REPRO_MISSING")

    def test_ledger_append_only_pin(self):
        led = FindingLedger(None)
        led.record({"finding": "占位", "repro": "复现", "evidence": "占位",
                    "found_at": "2026-11-20T09:00:00Z"})
        snapshot = led.entries()
        snapshot[0]["finding"] = "改（占位）"
        self.assertNotEqual(led.entries()[0]["finding"], "改（占位）")

    def test_vocab_closed(self):
        self.assertEqual(set(REPRO_VERDICTS), {"复现", "不复现"})
        self.assertEqual(set(HUNT_CONCLUSIONS),
                         {"有发现", "无可复现发现"})
        self.assertEqual(set(ERROR_CODES),
                         {"FINDING_LEDGER_DRIFT", "REPRO_MISSING",
                          "FP_ADMIT", "HUNT_VOCAB_GAP"})

    def test_ast_zero_network_zero_subprocess(self):
        banned = {"urllib", "requests", "socket", "http", "subprocess"}
        for f in (GATEWAY, GATE):
            src = f.read_text(encoding="utf-8")
            imported = set()
            for node in ast.walk(ast.parse(src)):
                if isinstance(node, ast.Import):
                    imported.update(a.name.split(".")[0]
                                    for a in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module.split(".")[0])
            self.assertFalse(imported & banned,
                             f"{f.name}: {imported & banned}")


if __name__ == "__main__":
    unittest.main()
