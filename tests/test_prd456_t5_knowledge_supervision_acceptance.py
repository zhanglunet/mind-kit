# -*- coding: utf-8 -*-
"""PRD-456/T5 测试（trend #2204 的 T5 环节）：知识监督台验收试运行。
运行：python3 -m pytest tests/test_prd456_t5_knowledge_supervision_acceptance.py -q
（仓库根执行；纯 unittest 用例，python3 -m unittest 亦可）
覆盖（T1 §7 验收标准 + T5 issue）：全链跑通（批注发回→改回 v2→点头→
过闸→只留点头过的知识进下游，三件套齐全）/未点头一律拦下、无记录的
记绕过告警、一批有拦即 vetoed/旧点头不放行新版/有未处理批注却点头即
拒绝/三件套缺件拒绝入账/验收脚本本身标准库-only、零网络零子进程。
零网络；全合成占位。
"""
import ast
import copy
import json
import subprocess
import sys
import unittest
from pathlib import Path

MOD_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(MOD_DIR))
from knowledge_supervision_acceptance import (  # noqa: E402
    ANNOTATION, ITEM_V1, ITEM_V2, SCHEMA,
    approve_with_unresolved_refused, happy_path,
    old_approval_does_not_admit_new_version, run_acceptance,
    three_records_complete, unapproved_blocked,
)
from knowledge_supervision_bench import (  # noqa: E402
    SupervisionLedger, revise, supervise,
)
from knowledge_supervision_gate import SupervisionGate  # noqa: E402

NOW = "2026-11-16T09:00:00Z"
LATER = "2026-11-16T10:00:00Z"
ACC_PATH = MOD_DIR / "knowledge_supervision_acceptance.py"
STDLIB_ALLOW = {"__future__", "copy", "json", "pathlib", "sys", "typing"}
FORBIDDEN_IDENTIFIERS = ("verify", "verif", "judge", "wiki", "store",
                         "edit", "patch", "rewrite", "collab", "session")


def _identifiers_of(path):
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


class TestAcceptanceVerdict(unittest.TestCase):
    def test_run_acceptance_all_scenarios_pass(self):
        """验收总 verdict 为“全链跑通”，5 个场景全过。"""
        report = run_acceptance()
        self.assertEqual(report["schema"], SCHEMA)
        self.assertEqual(report["verdict"], "全链跑通")
        self.assertEqual(report["passed_count"], report["total_count"])
        self.assertEqual(report["total_count"], 5)
        self.assertEqual(
            [s["name"] for s in report["scenarios"]],
            ["happy-path-full-chain", "unapproved-blocked",
             "old-approval-does-not-admit-new-version",
             "approve-with-unresolved-refused", "three-records-complete"])
        self.assertTrue(all(s["passed"] for s in report["scenarios"]))

    def test_acceptance_script_exits_zero(self):
        """验收脚本直接跑：退出码 0，stdout 是全链跑通的 JSON 报告。"""
        proc = subprocess.run(
            [sys.executable, str(ACC_PATH)], capture_output=True, text=True,
            cwd=str(Path(__file__).resolve().parents[1]), timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = json.loads(proc.stdout)
        self.assertEqual(report["verdict"], "全链跑通")


class TestHappyPath(unittest.TestCase):
    def test_full_chain_verdicts_and_versions(self):
        """全链裁决与版本：pending→returned→改回 v2 pending→approved。"""
        approved, sc = happy_path()
        self.assertTrue(sc["passed"])
        self.assertEqual(approved["knowledge_id"], "k-001")
        self.assertEqual(approved["verdict"], "approved")
        self.assertEqual(approved["version"], 2)
        self.assertEqual([s["step"] for s in approved["progress"]],
                         ["drafted", "approved"])

    def test_feedback_round_closed_by_revision(self):
        """发回闭环：改回来的版本记下回版对照，旧批注原样带到新版。"""
        returned = supervise(copy.deepcopy(ITEM_V1),
                             [copy.deepcopy(ANNOTATION)],
                             {"kind": "换来源", "text": "请换来源（占位）"},
                             at=NOW)
        revised = revise(returned, copy.deepcopy(ITEM_V2), at=LATER)
        self.assertEqual(revised["feedback_rounds"][0]["kind"], "换来源")
        self.assertEqual(revised["feedback_rounds"][0]["revised_knowledge_id"],
                         "k-001")
        self.assertEqual(revised["annotations"], returned["annotations"])
        self.assertEqual(revised["knowledge"]["sources"], ["来源 B（占位）"])

    def test_gate_pass_only_for_approved_version(self):
        """闸门只放行已点头的版本。"""
        approved, _ = happy_path()
        ledger = SupervisionLedger()
        ledger.record(approved)
        gate = SupervisionGate(ledger)
        self.assertEqual(gate.gate(copy.deepcopy(ITEM_V2), at=LATER)["decision"],
                         "pass")

    def test_outlet_only_approved(self):
        """下游出口只放行已点头的；待审的拦下留痕。"""
        approved, _ = happy_path()
        ledger = SupervisionLedger()
        ledger.record(approved)
        other = {"knowledge_id": "k-002", "version": 1,
                 "sources": ["来源占位"], "tags": ["标签占位"]}
        ledger.record(supervise(copy.deepcopy(other), at=NOW))
        outlet = ledger.outlet([copy.deepcopy(ITEM_V2),
                                copy.deepcopy(other)])
        self.assertEqual([p["knowledge_id"] for p in outlet["passed"]],
                         ["k-001"])
        self.assertEqual(outlet["blocked_count"], 1)


class TestNegativePaths(unittest.TestCase):
    def test_unapproved_blocked(self):
        """未点头一律拦下，无记录的记绕过告警。"""
        sc = unapproved_blocked()
        self.assertTrue(sc["passed"])
        self.assertIn("SUPERVISION_OUTLET_BYPASS", sc["detail"])

    def test_old_approval_does_not_admit_new_version(self):
        """v2 的点头不对 v3 有效。"""
        sc = old_approval_does_not_admit_new_version()
        self.assertTrue(sc["passed"])

    def test_approve_with_unresolved_refused(self):
        """有未处理批注却点头即拒绝。"""
        sc = approve_with_unresolved_refused()
        self.assertTrue(sc["passed"])

    def test_timeout_without_decision_never_passes(self):
        """超时未裁决不自动放行：一直 pending 的知识过闸即拦下。"""
        ledger = SupervisionLedger()
        ledger.record(supervise(copy.deepcopy(ITEM_V1),
                                [copy.deepcopy(ANNOTATION)], at=NOW))
        gate = SupervisionGate(ledger)
        out = gate.gate(copy.deepcopy(ITEM_V1), at=LATER)
        self.assertEqual(out["decision"], "block")
        self.assertEqual(out["reason"], "NOT_APPROVED")


class TestLedger(unittest.TestCase):
    def test_three_records_complete(self):
        """三件套落账齐全，缺件拒绝入账。"""
        self.assertTrue(three_records_complete()["passed"])

    def test_supervise_stores_item_verbatim(self):
        """监督台不产生新知识：入账内容与入项逐字节一致。"""
        rec = supervise(copy.deepcopy(ITEM_V1),
                        [copy.deepcopy(ANNOTATION)], at=NOW)
        self.assertEqual(rec["knowledge"], ITEM_V1)


class TestAcceptanceModuleHygiene(unittest.TestCase):
    def test_stdlib_only_and_no_network_or_subprocess(self):
        """验收脚本标准库-only；零网络零子进程。"""
        tree = ast.parse(ACC_PATH.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertLessEqual(
            imported,
            STDLIB_ALLOW | {"knowledge_supervision_bench",
                            "knowledge_supervision_gate"})
        self.assertFalse(imported & {"urllib", "requests", "socket",
                                     "http", "subprocess"}, ACC_PATH.name)

    def test_no_forbidden_identifiers(self):
        """验收脚本无越界标识符：不验真假、不碰下游载体、不下场改。"""
        names = _identifiers_of(ACC_PATH)
        for word in FORBIDDEN_IDENTIFIERS:
            hits = sorted(n for n in names if word in n)
            self.assertEqual(hits, [], f"出现 {word} 相关标识符：{hits}")

    def test_no_real_host_or_secret_placeholders(self):
        """验收脚本无真实内部主机名/IP/账号/密钥字面量（只用占位）。"""
        text = ACC_PATH.read_text(encoding="utf-8")
        for bad in ("10.", "192.168.", "api_key", "password", "token="):
            self.assertNotIn(bad, text)


if __name__ == "__main__":
    unittest.main()
