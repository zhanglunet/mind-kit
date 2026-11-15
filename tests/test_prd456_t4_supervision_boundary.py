# -*- coding: utf-8 -*-
"""PRD-456/T4测试（trend #2203 的 T4 环节）：知识监督台 划界断言。
运行：python -m pytest tests/test_prd456_t4_supervision_boundary.py -q（仓库根执行）
覆盖（T1 §2 非目标 + T4 issue）：监督台面零触碰下游载体（个人 Wiki（wiki/store）/
PRD-433 评审流水线 / PRD-410 知识共建会话 / PRD-387 入库知识验证台 零标识符——仅代码标识符扫描，docstring 提及不算）+借鉴仓
（plannotator/ag-ui/LoopForge）零符号+标准库-only 钉值+零网络零子进程+
不验真假钉值（无真假裁决词表/无 verify-judge 标识符/站不住的内容仍只
pending）+不产生新知识钉值（入账内容与入项逐字节一致/批注不改原文）+
人不下场改钉值（bench/gate 顶层方法面封闭，无 edit/patch/rewrite）+
不管共建会话钉值（无 collab/session 标识符/账本方法面封闭+append-only）
+闸门只守门钉值（只认 approved verdict，无放行开关参数/一批有拦即 vetoed）。
零网络；全合成占位。
"""
import ast
import copy
import inspect
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from knowledge_supervision_bench import (  # noqa: E402
    ANNOTATION_STATUSES, ANNOTATION_TYPES, ERROR_CODES,
    FEEDBACK_KINDS, PROGRESS_STEPS, SupervisionLedger, revise,
    supervise, VERDICTS,
)
from knowledge_supervision_gate import (  # noqa: E402
    DECISIONS, GATE_CODES, GATE_REASONS, GATE_SCHEMA, SupervisionGate,
)

NOW = "2026-11-16T09:00:00Z"
ITEM = {"knowledge_id": "k-001", "version": 1,
        "sources": ["来源 A（占位）"], "tags": ["标签甲（占位）"]}
FILLER = {"knowledge_id": "k-000", "version": 1,
          "sources": ["来源占位"], "tags": ["标签占位"]}

BENCH_MODULES = ["knowledge_supervision_bench.py", "knowledge_supervision_gate.py"]
STDLIB_ALLOW = {"__future__", "copy", "hashlib", "json", "pathlib", "typing"}


def _module_path(name):
    return Path(__file__).resolve().parents[1] / "scripts" / name


def _imports_of(path):
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    return imported


def _identifiers_of(path):
    """代码标识符（小写）：定义名/参数名/Name/Attribute；字符串字面量不算。"""
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            names.add(node.name.lower())
        elif isinstance(node, ast.arg):
            names.add(node.arg.lower())
        elif isinstance(node, ast.Name):
            names.add(node.id.lower())
        elif isinstance(node, ast.Attribute):
            names.add(node.attr.lower())
    return names


def _top_level_defs(path):
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    defs = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            defs.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    defs.add(t.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target,
                                                            ast.Name):
            defs.add(node.target.id)
    return defs


def _identifiers_all():
    merged = set()
    for mod in BENCH_MODULES:
        merged |= _identifiers_of(_module_path(mod))
    return merged


def _ledger_with(*records):
    led = SupervisionLedger(None)
    for rec in records:
        led.record(rec)
    return led


def _approved_ledger():
    return _ledger_with(supervise(copy.deepcopy(ITEM), approve=True, at=NOW))


class TestModuleIsolation(unittest.TestCase):
    def test_bench_gate_never_touch_downstream_carriers(self):
        """监督台面零触碰下游载体与三家邻台（PRD-433 评审流水线 / PRD-410 知识共建会话 / PRD-387 入库知识验证台）：相关标识符零出现。"""
        names = _identifiers_all()
        for word in ("verify", "review_pipeline", "collab", "session",
                     "transcript"):
            hits = sorted(n for n in names if word in n)
            self.assertEqual(hits, [], f"出现 {word} 相关标识符：{hits}")
        for exact in ("wiki", "store"):
            self.assertNotIn(exact, names, f"出现 {exact}")

    def test_borrowed_repos_zero_symbols(self):
        """借鉴仓（plannotator Apache-2.0/ag-ui MIT/LoopForge 无 LICENSE）
        零符号——只借形态（仅代码标识符扫描，docstring 提及不算）。"""
        names = _identifiers_all()
        for word in ("plannotator", "loopforge", "ag_ui", "agui"):
            hits = sorted(n for n in names if word in n)
            self.assertEqual(hits, [], f"出现 {word} 相关标识符：{hits}")

    def test_stdlib_only_and_no_network_or_subprocess(self):
        """标准库-only 钉值：bench+gate 静态导入全标准库；零网络零子进程。"""
        for mod in BENCH_MODULES:
            imported = _imports_of(_module_path(mod))
            self.assertLessEqual(imported, STDLIB_ALLOW, mod)
            self.assertFalse(imported & {"urllib", "requests", "socket",
                                         "http", "subprocess"}, mod)


class TestNoTruthVerification(unittest.TestCase):
    def test_verdict_vocab_has_no_truth_verdicts(self):
        """不验真假钉值：裁决词表只有 approved/returned/pending，无
        confirmed/false_positive/pass/blocked 等真假裁决。"""
        self.assertEqual(set(VERDICTS), {"approved", "returned", "pending"})
        self.assertEqual(set(ERROR_CODES), {"SUPERVISION_INCOMPLETE", "SUPERVISION_VERDICT_MISMATCH"})

    def test_no_verify_or_judge_identifiers(self):
        """不验真假钉值：bench+gate 无 verify/judge/复算类标识符。"""
        names = _identifiers_all()
        for word in ("verif", "judge", "recalc", "recompute", "confidence",
                     "score", "fact_check"):
            hits = sorted(n for n in names if word in n)
            self.assertEqual(hits, [], f"出现 {word} 相关标识符：{hits}")

    def test_bogus_content_still_only_pending(self):
        """不验真假钉值：站不住的内容（来源/说法存疑）进监督台仍只 pending，
        不出真假结论、不带真假字段。"""
        rec = supervise(copy.deepcopy(ITEM), [{"type": "疑问", "text": "来源查无出处（占位）"}], at=NOW)
        self.assertEqual(rec.get("verdict"), "pending")
        self.assertFalse(set(rec) & {"verified", "truth", "confidence",
                                     "score", "fact_checked"})
        self.assertIsNone(rec.get("refused"))

    def test_no_judge_or_verify_param_on_bench_surface(self):
        """不验真假钉值：bench 公开入口无 judge/verify 类参数。"""
        for fn in (supervise, revise):
            params = set(inspect.signature(fn).parameters)
            self.assertFalse(params & {"judge", "judge_fn", "verify",
                                       "verifier", "check_truth"}, fn.__name__)


class TestNoNewContent(unittest.TestCase):
    def test_supervise_stores_item_verbatim(self):
        """不产生新知识钉值：入账内容与入项逐字节一致，监督台不改写原文。"""
        rec = supervise(copy.deepcopy(ITEM), [{"type": "疑问", "text": "来源不明（占位）"}], at=NOW)
        self.assertEqual(rec["knowledge"], ITEM)
        self.assertEqual(rec["knowledge"]["tags"], ITEM["tags"])

    def test_annotations_do_not_rewrite_item_text(self):
        """不产生新知识钉值：批注只挂账，不改原文；改回来的版本旧批注原样带回。"""
        rec = supervise(copy.deepcopy(ITEM),
                          [{"type": "换来源", "text": "换一个来源（占位）"}],
                          at=NOW)
        self.assertEqual(rec["knowledge"], ITEM)
        returned = supervise(copy.deepcopy(ITEM),
                             [{"type": "换来源", "text": "换一个来源（占位）"}],
                             {"kind": "换来源", "text": "请换来源（占位）"},
                             at=NOW)
        self.assertEqual(returned["verdict"], "returned")
        back = revise(returned, dict(ITEM, version=2), at=NOW)
        self.assertEqual(back["annotations"], returned["annotations"])
        self.assertEqual(back["knowledge"], dict(ITEM, version=2))

    def test_no_generate_or_synthesize_identifiers(self):
        """不产生新知识钉值：bench+gate 无 generate/synthesize 类标识符。"""
        names = _identifiers_all()
        for word in ("generate", "synthesize", "summariz"):
            hits = sorted(n for n in names if word in n)
            self.assertEqual(hits, [], f"出现 {word} 相关标识符：{hits}")


class TestHumanNeverEdits(unittest.TestCase):
    def test_bench_gate_surface_closed(self):
        """人不下场改钉值：bench/gate 顶层方法面封闭，无 edit/patch/rewrite
        类入口；只有看（supervise）、批注、裁决（点头/发回）、改回（revise）。"""
        self.assertEqual(_top_level_defs(_module_path("knowledge_supervision_bench.py")),
                         {"SCHEMA", "VERDICTS", "PROGRESS_STEPS", "ANNOTATION_TYPES", "ANNOTATION_STATUSES", "FEEDBACK_KINDS", "ERROR_CODES", "SupervisionError", "_refused", "_unresolved", "_norm_annotations", "supervise", "revise", "SupervisionLedger"})
        self.assertEqual(_top_level_defs(_module_path("knowledge_supervision_gate.py")),
                         {"GATE_SCHEMA", "GATE_CODES", "GATE_REASONS", "DECISIONS", "GateError", "_anchor", "_unresolved", "SupervisionGate"})

    def test_no_edit_identifiers(self):
        """人不下场改钉值：bench+gate 无 edit/patch/rewrite 类标识符。"""
        names = _identifiers_all()
        for word in ("edit", "patch", "rewrite"):
            hits = sorted(n for n in names if word in n)
            self.assertEqual(hits, [], f"出现 {word} 相关标识符：{hits}")

    def test_no_collab_session_identifiers(self):
        """不管共建会话钉值：bench+gate 无 collab/session/同屏类标识符。"""
        names = _identifiers_all()
        for word in ("collab", "session", "coedit", "cowrite"):
            hits = sorted(n for n in names if word in n)
            self.assertEqual(hits, [], f"出现 {word} 相关标识符：{hits}")

    def test_ledger_surface_closed_and_append_only(self):
        """不管共建会话钉值：账本方法面封闭（record/entries/latest_for/
        outlet）+append-only，无删除/清空入口。"""
        led = SupervisionLedger(None)
        methods = {n for n in dir(led) if not n.startswith("_")}
        self.assertLessEqual(methods, {"record", "entries", "latest_for",
                                       "outlet"}, methods)
        led.record(supervise(copy.deepcopy(ITEM), at=NOW))
        mark_len = len(led.entries())
        led.record(supervise(copy.deepcopy(FILLER), at=NOW))
        self.assertEqual(len(led.entries()), mark_len + 1)


class TestGateOnlyGuards(unittest.TestCase):
    def test_gate_vocab_pins(self):
        """闸门只守门钉值：闸门词表封闭，只认 approved verdict。"""
        self.assertEqual(set(DECISIONS), {"pass", "block"})
        self.assertEqual(set(GATE_CODES),
                         {"SUPERVISION_INCOMPLETE",
                           "SUPERVISION_VERDICT_MISMATCH",
                           "SUPERVISION_OUTLET_BYPASS", "LEDGER_DRIFT"})
        self.assertEqual(set(GATE_REASONS), {"NOT_APPROVED", "VERSION_MISMATCH", "SUPERVISION_INCOMPLETE", "SUPERVISION_VERDICT_MISMATCH", "SUPERVISION_OUTLET_BYPASS", "LEDGER_DRIFT"})

    def test_gate_has_no_override_switch(self):
        """闸门只守门钉值：gate/gate_outlet 无 force/override/skip 类
        放行开关参数；闸门本身不改对象内容、不改状态。"""
        gate = SupervisionGate(_approved_ledger())
        for fn in (gate.gate, gate.gate_outlet):
            params = set(inspect.signature(fn).parameters)
            self.assertFalse(params & {"force", "override", "skip",
                                       "skip_gate", "allow_unapproved",
                                       "bypass"}, fn.__name__)
        names = _identifiers_of(_module_path("knowledge_supervision_gate.py"))
        for word in ("override", "force_pass"):
            hits = sorted(n for n in names if word in n)
            self.assertEqual(hits, [], f"出现 {word} 相关标识符：{hits}")

    def test_gate_pass_only_on_approved(self):
        """闸门只守门钉值：已点头才 pass，未点头一律 block；一批里有一条
        被拦即整批 vetoed，不存在部分放行当整批干净。"""
        gate = SupervisionGate(_approved_ledger())
        self.assertEqual(gate.gate(copy.deepcopy(ITEM), at=NOW)["decision"],
                         "pass")
        pending_led = _ledger_with(supervise(copy.deepcopy(ITEM), at=NOW))
        gate2 = SupervisionGate(pending_led)
        out = gate2.gate(copy.deepcopy(ITEM), at=NOW)
        self.assertEqual(out["decision"], "block")
        self.assertEqual(out["reason"], "NOT_APPROVED")
        batch = gate2.gate_outlet([copy.deepcopy(ITEM),
                                   copy.deepcopy(FILLER)], at=NOW)
        self.assertTrue(batch["vetoed"])
        self.assertEqual(batch["blocked_count"], 2)


if __name__ == "__main__":
    unittest.main()
