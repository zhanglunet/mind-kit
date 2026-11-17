# -*- coding: utf-8 -*-
"""PRD-515/T2 测试（trend #2496 的 T2 环节）：知识条目技能契约。
运行：uv run --with pytest python -m pytest tests/test_knowledge_skill_contract.py -q
覆盖（T1 §4/§5 + R1~R4）：五件套校验/无契约拒绝/参数 schema 校验/
前置条件检查/失败显式 NOT_COMPUTED/回退先问人/JSONL 落库/AST 零网络。
零网络；全合成占位。
"""
import ast
import json
import sys
import tempfile
import unittest
from pathlib import Path

MOD_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(MOD_DIR))
from knowledge_skill_contract import (  # noqa: E402
    CONTRACT_SCHEMA, LEGAL_FALLBACK, LEGAL_FAILURE, REQUIRED_KEYS,
    ContractError, ContractLedger, register_contract, validate_call,
    validate_contract,
)

NOW = "2026-11-17T09:00:00Z"
CONTRACT = {
    "schema": CONTRACT_SCHEMA,
    "contract_id": "contract-knowledge-001",
    "skill_name": "knowledge_skill（占位）",
    "tools": ["knowledge_read（占位）", "knowledge_compute（占位）"],
    "input_schema": {"input": "…（占位）", "version": "v1（占位）"},
    "output_schema": {"conclusion": "string", "cited": ["knowledge（占位）"]},
    "preconditions": {"schema_version_present": True},
    "failure_semantics": "NOT_COMPUTED",
    "fallback": "ask_human",
}
CALL_PARAMS = {"input": "…（占位）", "version": "v1（占位）",
               "schema_version_present": True}


class TestContractValidation(unittest.TestCase):
    def test_valid_contract_passes(self):
        self.assertEqual(validate_contract(CONTRACT), [])

    def test_incomplete_refused(self):
        bad = dict(CONTRACT)
        del bad["tools"]
        problems = validate_contract(bad)
        self.assertTrue(any("CONTRACT_INCOMPLETE" in p for p in problems))

    def test_failure_semantics_must_be_not_computed(self):
        bad = dict(CONTRACT, failure_semantics="guess_a_number")
        problems = validate_contract(bad)
        self.assertTrue(any("CONTRACT_FAILURE_AMBIGUOUS" in p for p in problems))

    def test_fallback_vocab(self):
        bad = dict(CONTRACT, fallback="guess")
        problems = validate_contract(bad)
        self.assertTrue(any("CONTRACT_INCOMPLETE" in p for p in problems))

    def test_register_rejects_incomplete(self):
        bad = dict(CONTRACT)
        del bad["fallback"]
        with self.assertRaisesRegex(ContractError, "CONTRACT_INCOMPLETE"):
            register_contract(bad)


class TestValidateCall(unittest.TestCase):
    def test_valid_call_allowed(self):
        out = validate_call(CONTRACT, CALL_PARAMS)
        self.assertTrue(out["allowed"])

    def test_no_contract_refused(self):
        out = validate_call(None, CALL_PARAMS)
        self.assertFalse(out["allowed"])
        self.assertEqual(out["reason"], "CONTRACT_MISSING")

    def test_missing_input_field_refused(self):
        params = {"input": "…（占位）"}   # 缺 version
        out = validate_call(CONTRACT, params)
        self.assertFalse(out["allowed"])
        self.assertEqual(out["reason"], "CONTRACT_VALIDATION_FAILED")

    def test_precondition_failure_triggers_fallback(self):
        params = dict(CALL_PARAMS, schema_version_present=False)
        out = validate_call(CONTRACT, params)
        self.assertFalse(out["allowed"])
        self.assertIn("ask_human", out["detail"])


class TestLedger(unittest.TestCase):
    def test_jsonl_append_only(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "contracts" / "log.jsonl"
            led = ContractLedger(path)
            led.record(skill_name="knowledge_skill（占位）",
                       call_params=CALL_PARAMS, contract=CONTRACT, at=NOW)
            led.record(skill_name="unknown（占位）", call_params=CALL_PARAMS,
                       contract=None, at=NOW)
            self.assertEqual(len(led.entries()), 2)
            lines = path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 2)
            self.assertFalse(json.loads(lines[1])["allowed"])

    def test_failure_semantics_legal(self):
        self.assertEqual(LEGAL_FAILURE, "NOT_COMPUTED")
        self.assertIn("ask_human", LEGAL_FALLBACK)


class TestRedline(unittest.TestCase):
    def test_ast_zero_network(self):
        banned = {"urllib", "requests", "socket", "http", "subprocess"}
        src = (Path(__file__).resolve().parents[1] / "scripts" / "knowledge_skill_contract.py").read_text(encoding="utf-8")
        imported = set()
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertFalse(imported & banned, imported & banned)

    def test_schema_closed(self):
        self.assertEqual(CONTRACT_SCHEMA, "knowledge-skill-contract/v1")
        self.assertEqual(len(REQUIRED_KEYS), 6)   # 五件套+contract_id


if __name__ == "__main__":
    unittest.main()
