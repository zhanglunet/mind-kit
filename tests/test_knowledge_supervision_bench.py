# -*- coding: utf-8 -*-
"""PRD-456/T2 测试（trend #2201 的 T2 环节）：知识监督台。
运行：python -m pytest tests/test_knowledge_supervision_bench.py -q（仓库根执行）
覆盖（T1 §3-§4）：三件套落账/三个接入点/批注词表与发回引用/点头双向对账/
改完回来版本+1 且旧批注不丢/outlet 拦截/JSONL 落库/词表封闭/AST 零网络。
零网络；全合成占位。
"""
import ast
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
MOD_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import json
from knowledge_supervision_bench import (  # noqa: E402
    ANNOTATION_STATUSES, ANNOTATION_TYPES, ERROR_CODES, FEEDBACK_KINDS,
    PROGRESS_STEPS, VERDICTS, SupervisionError, SupervisionLedger,
    revise, supervise,
)

NOW = "2026-11-15T09:00:00Z"
ITEM = {"knowledge_id": "k-001", "version": 1, "sources": ["来源 A（占位）"], "tags": ["标签甲（占位）"], "steps": ["来源清单", "标签选择", "知识初版"]}
ANNOTATIONS = [
    {"anchor": "来源 A", "text": "换来源，不可信（占位）",
     "type": "换来源", "author": "reviewer-placeholder", "at": NOW},
    {"anchor": "标签甲", "text": "标签是否太泛（占位）",
     "type": "疑问", "author": "reviewer-placeholder", "at": NOW},
]
FEEDBACK = {"kind": "换来源", "text": "换来源，补一条可溯源来源（占位）",
            "annotation_ids": ["a-001", "a-002"]}


class TestSupervise(unittest.TestCase):
    def test_minimal_pending(self):
        out = supervise(ITEM, at=NOW)
        self.assertEqual(out["verdict"], "pending")
        self.assertEqual(out["version"], 1)
        self.assertEqual([s["step"] for s in out["progress"]], ["drafted"])
        self.assertEqual(out["annotations"], [])
        self.assertEqual(out["feedback_rounds"], [])

    def test_missing_id_refused(self):
        bad = dict(ITEM)
        del bad["knowledge_id"]
        out = supervise(bad, at=NOW)
        self.assertEqual(out["refused"], "SUPERVISION_INCOMPLETE")

    def test_annotations_normalized(self):
        out = supervise(ITEM, ANNOTATIONS, at=NOW)
        self.assertEqual(len(out["annotations"]), 2)
        self.assertEqual(out["annotations"][0]["annotation_id"], "a-001")
        self.assertEqual(out["annotations"][0]["status"], "待处理")
        self.assertEqual(out["annotations"][1]["type"], "疑问")

    def test_unknown_annotation_type_refused(self):
        out = supervise(ITEM, [{"text": "x（占位）", "type": "不存在"}],
                        at=NOW)
        self.assertEqual(out["refused"], "SUPERVISION_INCOMPLETE")

    def test_empty_annotation_text_refused(self):
        out = supervise(ITEM, [{"text": "  ", "type": "疑问"}], at=NOW)
        self.assertEqual(out["refused"], "SUPERVISION_INCOMPLETE")

    def test_feedback_returns(self):
        out = supervise(ITEM, ANNOTATIONS, FEEDBACK, at=NOW)
        self.assertEqual(out["verdict"], "returned")
        self.assertEqual([s["step"] for s in out["progress"]],
                         ["drafted", "returned"])
        self.assertEqual(out["feedback_rounds"][0]["round"], 1)
        self.assertEqual(out["feedback_rounds"][0]["kind"], "换来源")
        self.assertEqual(out["feedback_rounds"][0]["annotation_ids"],
                         ["a-001", "a-002"])

    def test_feedback_unknown_kind_refused(self):
        out = supervise(ITEM, ANNOTATIONS,
                        {"kind": "不存在", "text": "x（占位）"}, at=NOW)
        self.assertEqual(out["refused"], "SUPERVISION_INCOMPLETE")

    def test_feedback_unknown_annotation_refused(self):
        out = supervise(ITEM, ANNOTATIONS,
                        {"kind": "换来源", "text": "x（占位）",
                         "annotation_ids": ["a-999"]}, at=NOW)
        self.assertEqual(out["refused"], "SUPERVISION_INCOMPLETE")

    def test_approve_blocked_by_unresolved(self):
        out = supervise(ITEM, ANNOTATIONS, approve=True, at=NOW)
        self.assertEqual(out["refused"], "SUPERVISION_VERDICT_MISMATCH")

    def test_approve_after_resolving(self):
        resolved = [dict(a, status="已采纳") for a in ANNOTATIONS]
        out = supervise(ITEM, resolved, approve=True, at=NOW)
        self.assertEqual(out["verdict"], "approved")
        self.assertEqual([s["step"] for s in out["progress"]],
                         ["drafted", "approved"])

    def test_approve_with_feedback_refused(self):
        out = supervise(ITEM, ANNOTATIONS, FEEDBACK, approve=True, at=NOW)
        self.assertEqual(out["refused"], "SUPERVISION_VERDICT_MISMATCH")

    def test_vocabs_closed(self):
        self.assertEqual(set(VERDICTS), {"approved", "returned", "pending"})
        self.assertEqual(set(PROGRESS_STEPS),
                         {"drafted", "returned", "revised", "approved"})
        self.assertEqual(set(ANNOTATION_TYPES), {"换来源", "补标签", "疑问", "通过"})
        self.assertEqual(set(ANNOTATION_STATUSES), {"待处理", "已采纳", "已驳回"})
        self.assertEqual(set(FEEDBACK_KINDS), {"换来源", "补标签", "只改指定处"})


class TestRevise(unittest.TestCase):
    def test_revise_carries_annotations(self):
        base = supervise(ITEM, ANNOTATIONS, FEEDBACK, at=NOW)
        revised_item = dict(ITEM, version=2)
        out = revise(base, revised_item, at=NOW)
        self.assertEqual(out["verdict"], "pending")
        self.assertEqual(out["version"], 2)
        self.assertEqual([s["step"] for s in out["progress"]],
                         ["drafted", "returned", "revised"])
        self.assertEqual(len(out["annotations"]), 2)
        self.assertEqual(out["annotations"][0]["status"], "待处理")
        self.assertEqual(out["feedback_rounds"][0]["revised_knowledge_id"],
                         "k-001")

    def test_revise_from_non_returned_refused(self):
        base = supervise(ITEM, at=NOW)
        out = revise(base, dict(ITEM, version=2), at=NOW)
        self.assertEqual(out["refused"], "SUPERVISION_INCOMPLETE")

    def test_revise_wrong_version_refused(self):
        base = supervise(ITEM, ANNOTATIONS, FEEDBACK, at=NOW)
        out = revise(base, dict(ITEM, version=3), at=NOW)
        self.assertEqual(out["refused"], "SUPERVISION_INCOMPLETE")


class TestLedgerOutlet(unittest.TestCase):
    def test_jsonl_persistence_append_only(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "supervision" / "ledger.jsonl"
            led = SupervisionLedger(path)
            led.record(supervise(ITEM, ANNOTATIONS, FEEDBACK, at=NOW))
            led.record(supervise(dict(ITEM, knowledge_id="k-002"),
                                 approve=True, at=NOW))
            self.assertEqual(len(led.entries()), 2)
            lines = path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 2)
            self.assertEqual(json.loads(lines[0])["knowledge_id"],
                             "k-001")

    def test_record_refused_raises(self):
        led = SupervisionLedger(None)
        bad = supervise(ITEM, [{"text": "x（占位）", "type": "不存在"}],
                        at=NOW)
        with self.assertRaisesRegex(SupervisionError,
                                    "SUPERVISION_INCOMPLETE"):
            led.record(bad)

    def test_verdict_mismatch_raises(self):
        led = SupervisionLedger(None)
        out = supervise(ITEM, ANNOTATIONS, FEEDBACK, at=NOW)
        bad = dict(out, verdict="approved")
        with self.assertRaisesRegex(SupervisionError,
                                    "SUPERVISION_VERDICT_MISMATCH"):
            led.record(bad)

    def test_outlet_only_approved_passes(self):
        led = SupervisionLedger(None)
        led.record(supervise(ITEM, ANNOTATIONS, FEEDBACK, at=NOW))
        led.record(supervise(dict(ITEM, knowledge_id="k-002"),
                             approve=True, at=NOW))
        out = led.outlet([ITEM, dict(ITEM, knowledge_id="k-002"),
                          dict(ITEM, knowledge_id="k-003")])
        self.assertEqual([d["knowledge_id"] for d in out["passed"]],
                         ["k-002"])
        self.assertEqual(out["blocked_count"], 2)
        self.assertEqual(out["blocked"][0]["verdict"], "returned")
        self.assertIsNone(out["blocked"][1]["verdict"])


class TestRedline(unittest.TestCase):
    def test_ast_zero_network_zero_subprocess(self):
        banned = {"urllib", "requests", "socket", "http", "subprocess"}
        src = MOD_DIR / "knowledge_supervision_bench.py"
        tree = ast.parse(Path(src).read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertFalse(imported & banned, imported & banned)

    def test_error_codes_closed(self):
        self.assertEqual(set(ERROR_CODES),
                         {"SUPERVISION_INCOMPLETE",
                          "SUPERVISION_VERDICT_MISMATCH"})


if __name__ == "__main__":
    unittest.main()
