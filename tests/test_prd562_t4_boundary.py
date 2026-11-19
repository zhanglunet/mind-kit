# -*- coding: utf-8 -*-
"""PRD-562/T4 测试（trend #2661 的 T4 环节）：准入检查划界断言。
运行：uv run --with pytest python -m pytest skill/mind-kit/scripts/test_prd562_t4_boundary.py -q
按 PRD 任务拆分 T4 行：准入检查与方法论包/契约/评估/评审流水线/监督回路
的边界断言；检查只出结论不代行准入。
覆盖：借鉴仓（superpowers/bughunter/cli-anything）零符号+机器不代行准入
钉值+AST 零网络零子进程+词表封闭。零网络；全合成占位。
"""
import ast
import sys
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[0]
sys.path.insert(0, str(SRC))
MODULE_DIR = SRC
GATEWAY = MODULE_DIR / "mindkit_admission.py"
GATE = MODULE_DIR / "mindkit_admission_gate.py"

BORROWED = ("superpowers", "bughunter", "cli_anything", "cli-anything")
NEIGHBOR = ("methodology", "admission_check_placeholder",
            "contract", "evaluation", "review_pipeline",
            "supervision")


class TestBorrowed(unittest.TestCase):
    def test_borrowed_zero_symbols(self):
        """借鉴仓（superpowers/bughunter/cli-anything）零符号。"""
        for f in (GATEWAY, GATE):
            tree = ast.parse(f.read_text(encoding="utf-8"))
            names = {n.name.lower() for n in ast.walk(tree)
                     if isinstance(n, (ast.ClassDef, ast.FunctionDef))}
            for word in BORROWED:
                self.assertNotIn(word, names, f"{f.name} 出现 {word}")


class TestNoAutoAdmit(unittest.TestCase):
    def test_no_adapprove_symbol(self):
        """机器不代行准入：无 approve/admit/publish 符号。"""
        for f in (GATEWAY, GATE):
            names = _names_of(f)
            for word in ("approve", "admit_", "publish"):
                self.assertNotIn(word, names, f"{f.name} 出现 {word}")

    def test_admission_vocab_closed(self):
        """准入结论词表封闭（四值）。"""
        from mindkit_admission_gate import check_no_auto_admit
        for a in ("可进收件箱", "不进（整改）", "待复核", "待补测"):
            self.assertEqual(check_no_auto_admit(a)["gate"], "pass")
        d = check_no_auto_admit("自动准入")
        self.assertEqual(d["gate"], "block")


class TestOneVotePin(unittest.TestCase):
    def test_one_vote_bypass_refused(self):
        """一票否决不可绕。"""
        from mindkit_admission_gate import check_one_vote
        d = check_one_vote([{"layer": "L1_quality", "verdict": "不过"}],
                           "可进收件箱")
        self.assertEqual(d["gate"], "block")
        self.assertEqual(d["reasons"][0]["code"], "ONE_VOTE_BYPASS")


class TestZeroNet(unittest.TestCase):
    def test_ast_zero_network(self):
        banned = {"urllib", "requests", "socket", "http", "subprocess"}
        for f in (GATEWAY, GATE):
            imported = _imports_of(f)
            self.assertFalse(imported & banned,
                             f"{f.name} 导入 {imported & banned}")

    def test_ast_zero_subprocess(self):
        for f in (GATEWAY, GATE):
            src = f.read_text(encoding="utf-8")
            self.assertNotIn("subprocess", src, f.name)


def _names_of(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {n.name.lower() for n in ast.walk(tree)
            if isinstance(n, (ast.ClassDef, ast.FunctionDef))}


def _imports_of(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    return imported


if __name__ == "__main__":
    unittest.main()
