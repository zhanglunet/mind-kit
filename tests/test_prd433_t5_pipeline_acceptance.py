# -*- coding: utf-8 -*-
"""PRD-433/T5 测试（trend #2085 的 T5 环节）：知识条目评审流水线 验收试运行。
运行：uv run --with pytest python -m pytest tests/test_knowledge_review_pipeline.py -q
验收（T1 §6 T5 行「全链两遍逐字节一致+失败演练+链复跑+文档无密钥」）：
  接入点全链演练：草稿 → run_pipeline（规则扫候选+judge 判定）→ 落账 →
  outlet（pass 进 个人 Wiki）→ 闸门全 pass；两遍逐字节一致（确定性可复现）；
  失败演练：blocked 拦截留痕/未全判拒绝/账本删除 LEDGER_DRIFT；链复跑
  T2/T3/T4 子进程 exit 0；文档无密钥：T1 设计文档拼接 needle 扫描+占位符
  纪律（R5）。零网络；全合成占位。
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
MOD_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from knowledge_review_pipeline import (  # noqa: E402
    PipelineError, ReviewPipelineLedger, run_pipeline)
from knowledge_review_pipeline_gates import (  # noqa: E402
    append_only_gate, coverage_gate, gate_summary, mark_baseline, verdict_gate)

NOW = "2026-11-14T12:00:00Z"
DRAFT = {"draft_id": "d-001", "references": ["R1"], "lines": [
    {"no": 1, "kind": "number", "text": "指标=42（占位）",
     "num": {"stated": 42, "recomputed": 41}},
    {"no": 2, "kind": "text", "text": "本段沿用旧口径（占位）表述"},
    {"no": 3, "kind": "reference", "text": "见 [ref:R1]（占位）与 [ref:R9]（占位）"},
]}


def judge_all_confirm(candidates):
    return [dict(c, verdict="confirmed", note="确认（占位）")
            for c in candidates]


def judge_all_reject(candidates):
    return [dict(c, verdict="false_positive", note="误报（占位）")
            for c in candidates]


def full_chain():
    """接入点全链：草稿→流水线→落账→出口→闸门。"""
    led = ReviewPipelineLedger(None)
    out = run_pipeline(DRAFT, judge_all_confirm, at=NOW)
    led.record(out)
    outlet = led.outlet([DRAFT])
    with tempfile.TemporaryDirectory() as td:
        disk = ReviewPipelineLedger(Path(td) / "review" / "log.jsonl")
        disk.record(run_pipeline(DRAFT, judge_all_confirm, at=NOW))
        gates = [append_only_gate(disk), verdict_gate(disk.entries()[0]),
                 coverage_gate(disk.entries()[0])]
        return {"out": out, "outlet": outlet, "disk_events": disk.entries(),
                "summary": gate_summary(gates)}


class TestFullChainDrill(unittest.TestCase):
    def test_chain_twice_byte_identical(self):
        runs = [full_chain(), full_chain()]
        self.assertEqual(json.dumps(runs[0], sort_keys=True),
                         json.dumps(runs[1], sort_keys=True))
        self.assertEqual(runs[0]["summary"]["gate"], "pass")
        self.assertEqual(runs[0]["out"]["verdict"], "blocked")
        self.assertEqual(runs[0]["outlet"]["blocked_count"], 1)

    def test_pass_chain_green_to_outlet(self):
        led = ReviewPipelineLedger(None)
        led.record(run_pipeline(dict(DRAFT, draft_id="d-ok", lines=[
            {"no": 1, "kind": "number", "text": "指标=41（占位）",
             "num": {"stated": 41, "recomputed": 41}},
            {"no": 2, "kind": "reference", "text": "见 [ref:R1]（占位）"}]),
            judge_all_reject, at=NOW))
        out = led.outlet([dict(DRAFT, draft_id="d-ok")])
        self.assertEqual(len(out["passed"]), 1)
        self.assertEqual(out["blocked_count"], 0)


class TestFailureDrills(unittest.TestCase):
    def test_blocked_traced_not_in_outlet(self):
        led = ReviewPipelineLedger(None)
        out = run_pipeline(dict(DRAFT, draft_id="d-bad"), judge_all_confirm,
                           at=NOW)
        led.record(out)
        outlet = led.outlet([dict(DRAFT, draft_id="d-bad")])
        self.assertEqual(outlet["passed"], [])
        self.assertEqual(outlet["blocked"][0]["verdict"], "blocked")
        self.assertTrue(any(j["verdict"] == "confirmed"
                            for j in led.entries()[0]["judgments"]))

    def test_partial_judgment_refused_and_unrecorded(self):
        led = ReviewPipelineLedger(None)

        def judge_half(cands):
            return [dict(cands[0], verdict="confirmed", note="n")]

        out = run_pipeline(DRAFT, judge_half, at=NOW)
        self.assertEqual(out["refused"], "REVIEW_INCOMPLETE")
        with self.assertRaises(PipelineError):
            led.record(out)
        self.assertEqual(led.entries(), [])

    def test_log_deletion_drift_drill(self):
        led = ReviewPipelineLedger(None)
        led.record(run_pipeline(DRAFT, judge_all_confirm, at=NOW))
        mark_baseline(led)
        led._records.pop()
        self.assertEqual(append_only_gate(led)["gate"], "LEDGER_DRIFT")


class TestChainRerun(unittest.TestCase):
    def test_t2_t3_t4_rerun_green(self):
        """链复跑：T2/T3/T4 测试子进程复跑 exit 0（链上仍绿实测）。"""
        for name in ("test_knowledge_review_pipeline.py", "test_knowledge_review_pipeline_gates.py", "test_prd433_t4_pipeline_boundary.py"):
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", str(SCRIPTS / name)], capture_output=True, timeout=300)
            self.assertEqual(proc.returncode, 0,
                             f"{name} 复跑失败：{proc.stdout[-400:]}")


class TestDocNoSecrets(unittest.TestCase):
    def test_t1_design_doc_no_secrets(self):
        """文档无密钥：T1 设计文档拼接 needle 扫描+占位符纪律（R5）。"""
        repo = Path(__file__).resolve().parents[1]
        doc = next(repo.glob("docs/plans/2026-11-14-prd-433-*.md"))
        text = doc.read_text(encoding="utf-8").lower()
        for needle in ("sk-" + "live", "passw" + "ord", "api_k" + "ey"):
            self.assertNotIn(needle, text, f"设计文档出现密钥词 {needle}")
        self.assertIn("占位", text)


if __name__ == "__main__":
    unittest.main()
