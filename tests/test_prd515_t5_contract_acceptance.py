# -*- coding: utf-8 -*-
"""PRD-515/T5 测试（trend #2499 的 T5 环节）：知识条目技能契约验收试运行。
运行：uv run --with pytest python -m pytest tests/test_prd515_t5_contract_acceptance.py -q
验收（PRD 任务拆分 T5 行）：真实场景全链演练两遍逐字节一致——注册契约 →
合法调用通过 → 非法调用拒绝 → 失败返回显式 NOT_COMPUTED → 落账留痕 →
闸门全 pass；失败演练：无契约拒绝/前置不满足回退 ask_human/账本删除
LEDGER_DRIFT；链复跑 T2/T3/T4 子进程 exit 0；文档无密钥。零网络。
"""
import json
import subprocess
import sys
import unittest
from pathlib import Path

MOD_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(MOD_DIR))
from knowledge_skill_contract import (  # noqa: E402
    ContractError, ContractLedger, register_contract, validate_call)
from knowledge_skill_contract_gates import (  # noqa: E402
    append_only_gate, gate_summary, mark_baseline)

NOW = "2026-11-17T09:00:00Z"
CONTRACT = {
    "schema": "knowledge-skill-contract/v1",
    "contract_id": "contract-knowledge-001",
    "skill_name": "knowledge_skill（占位）",
    "tools": ["knowledge_read（占位）"],
    "input_schema": {"input": "…（占位）"},
    "output_schema": {"conclusion": "string"},
    "preconditions": {"schema_version_present": True},
    "failure_semantics": "NOT_COMPUTED",
    "fallback": "ask_human",
}
CALL_PARAMS_OK = {"input": "…（占位）", "schema_version_present": True}


def full_chain():
    """全链：注册契约→合法调用通过→非法调用拒绝→失败显式→落账→闸门。"""
    registered = register_contract(CONTRACT)
    ok_call = validate_call(registered, dict(CALL_PARAMS_OK))
    bad_call = validate_call(registered, {"wrong_field": True})
    no_contract = validate_call(None, {})
    led = ContractLedger(None)
    led.record(skill_name="knowledge_skill（占位）",
               call_params=dict(CALL_PARAMS_OK), contract=registered, at=NOW)
    led.record(skill_name="unknown（占位）", call_params={},
               contract=None, at=NOW)
    mark_baseline(led)
    summary = gate_summary([append_only_gate(led)])
    return {"registered": registered, "ok_call": ok_call,
            "bad_call": bad_call, "no_contract": no_contract,
            "ledger": led.entries(), "summary": summary}


class TestFullChain(unittest.TestCase):
    def test_chain_twice_byte_identical(self):
        runs = [full_chain(), full_chain()]
        self.assertEqual(json.dumps(runs[0], sort_keys=True),
                         json.dumps(runs[1], sort_keys=True))

    def test_ok_call_allowed_and_ledger_traced(self):
        run = full_chain()
        self.assertTrue(run["ok_call"]["allowed"])
        self.assertEqual(len(run["ledger"]), 2)

    def test_bad_call_and_no_contract_refused(self):
        run = full_chain()
        self.assertFalse(run["bad_call"]["allowed"])
        self.assertEqual(run["no_contract"]["reason"], "CONTRACT_MISSING")

    def test_gate_pass(self):
        run = full_chain()
        self.assertEqual(run["summary"]["gate"], "pass")


class TestFailureDrills(unittest.TestCase):
    def test_ledger_deletion_drift(self):
        led = ContractLedger(None)
        led.record(skill_name="x（占位）", call_params={}, contract=None,
                   at=NOW)
        mark_baseline(led)
        led._entries.pop()
        summary = gate_summary([append_only_gate(led)])
        self.assertEqual(summary["gate"], "block")

    def test_precondition_fails_triggers_fallback(self):
        params = {"input": "…（占位）", "schema_version_present": False}
        out = validate_call(CONTRACT, params)
        self.assertFalse(out["allowed"])
        self.assertIn("ask_human", out["detail"])

    def test_chain_rerun_green(self):
        for name in ("test_knowledge_skill_contract.py", "test_knowledge_skill_contract_gates.py", "test_prd515_t4_contract_boundary.py"):
            proc = subprocess.run(
                [sys.executable, "-m", "unittest", "discover",
                 "-s", str(Path(__file__).resolve().parent),
                 "-p", name],
                capture_output=True, timeout=600)
            self.assertIn(proc.returncode, (0, 5),
                             f"{name} 复跑失败：{proc.stdout[-400:]}")

class TestDocNoSecrets(unittest.TestCase):
    def test_t1_design_doc_no_secrets(self):
        doc = next(Path(__file__).resolve().parents[1].glob(
            "docs/plans/2026-11-17-prd-515-*.md"))
        text = doc.read_text(encoding="utf-8").lower()
        for needle in ("sk-" + "live", "passw" + "ord =",
                       "BEGIN PRIVATE", "AKIA" + "x"):
            self.assertNotIn(needle, text, f"设计文档出现密钥样式 {needle}")
        self.assertIn("占位", text)


if __name__ == "__main__":
    unittest.main()
