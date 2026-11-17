# -*- coding: utf-8 -*-
"""PRD-515/T2（trend issue #2496 的 T2 环节）：知识条目技能契约最小实现。

按 T1 设计（docs/plans/2026-11-17-prd-515-knowledge-skill-contract-design.md）§4/§5 落地：
  - register_contract(contract)：五件套缺一 CONTRACT_INCOMPLETE 拒绝注册；
  - validate_call(contract, call_params)：调用参数 vs input_schema 校验 +
    前置条件检查；不过 → CONTRACT_VALIDATION_FAILED 拒绝调用；
  - no contract → CONTRACT_MISSING 拒绝（R1 无契约的技能不进个人 Wiki）；
  - ContractLedger：JSONL append-only 路径注入落账（R3）；
  - failure_semantics="NOT_COMPUTED" 硬编码为合法失败返回值（R3）；
  - fallback="ask_human" 时返回回退指引（R4 口径缺失时先问人）。
零网络零子进程；示例全虚构占位。
测试：test_knowledge_skill_contract.py
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

CONTRACT_SCHEMA = "knowledge-skill-contract/v1"
REQUIRED_KEYS = ("tools", "input_schema", "output_schema", "preconditions",
                 "failure_semantics", "fallback")
LEGAL_FAILURE = "NOT_COMPUTED"
LEGAL_FALLBACK = ("ask_human", "use_previous", "skip")
ERROR_CODES = ("CONTRACT_MISSING", "CONTRACT_INCOMPLETE",
               "CONTRACT_VALIDATION_FAILED", "CONTRACT_FAILURE_AMBIGUOUS")


class ContractError(ValueError):
    """契约违规——显形拒绝。"""


def _require(ok: bool, code: str, detail: str) -> None:
    if not ok:
        raise ContractError(f"{code}：{detail}")


def validate_contract(contract: dict[str, Any]) -> list[str]:
    """五件套校验：返回问题列表（空=通过）。"""
    problems = []
    if not isinstance(contract, dict):
        return ["contract 非对象"]
    for key in REQUIRED_KEYS:
        v = contract.get(key)
        if v is None or v == "" or v == [] or v == {}:
            problems.append(f"五件套缺 {key}（CONTRACT_INCOMPLETE）")
    if contract.get("failure_semantics") not in (None, LEGAL_FAILURE):
        problems.append(
            f"failure_semantics {contract.get('failure_semantics')!r} "
            f"≠ {LEGAL_FAILURE!r}——失败必须显式'未算出'而非瞎编"
            "（CONTRACT_FAILURE_AMBIGUOUS）")
    if contract.get("fallback") not in (None,) + LEGAL_FALLBACK:
        problems.append(
            f"fallback {contract.get('fallback')!r} 词表外 {LEGAL_FALLBACK}"
            "（CONTRACT_INCOMPLETE）")
    return problems


def register_contract(contract: dict[str, Any]) -> dict[str, Any]:
    """注册契约：五件套齐才收，缺一拒绝（R2）。"""
    problems = validate_contract(contract)
    if problems:
        raise ContractError("; ".join(problems))
    return copy.deepcopy(contract)


def validate_call(contract: dict[str, Any] | None,
                  call_params: dict[str, Any]) -> dict[str, Any]:
    """调用前校验（R1/R4）：无契约拒绝；参数与 schema 校验+前置条件检查。"""
    if contract is None:
        return {"schema": CONTRACT_SCHEMA, "allowed": False,
                "reason": "CONTRACT_MISSING",
                "detail": "无契约的技能不进个人 Wiki（R1）"}
    problems = validate_contract(contract)
    if problems:
        return {"schema": CONTRACT_SCHEMA, "allowed": False,
                "reason": "CONTRACT_INCOMPLETE",
                "detail": "; ".join(problems)}
    input_schema = contract.get("input_schema") or {}
    for field in input_schema:
        if field not in call_params:
            return {"schema": CONTRACT_SCHEMA, "allowed": False,
                    "reason": "CONTRACT_VALIDATION_FAILED",
                    "detail": f"调用参数缺 input_schema 字段 {field!r}"}
    preconds = contract.get("preconditions") or {}
    for cond, expected in preconds.items():
        if call_params.get(cond) != expected:
            return {"schema": CONTRACT_SCHEMA, "allowed": False,
                    "reason": "CONTRACT_VALIDATION_FAILED",
                    "detail": f"前置条件 {cond!r} 不满足——回退 {contract.get('fallback', 'ask_human')}"}
    return {"schema": CONTRACT_SCHEMA, "allowed": True, "reason": "ok"}


class ContractLedger:
    """契约校验结果落账（R3）：JSONL append-only，路径注入。"""

    def __init__(self, path: str | Path | None = None) -> None:
        self._entries: list[dict[str, Any]] = []
        self._path = Path(path) if path else None

    def record(self, *, skill_name: str, call_params: dict[str, Any],
               contract: dict[str, Any] | None, at: str = "") -> dict[str, Any]:
        verdict = validate_call(contract, call_params)
        entry = {"schema": CONTRACT_SCHEMA, "skill_name": str(skill_name),
                 "at": str(at),
                 "allowed": verdict.get("allowed", False),
                 "reason": verdict.get("reason", ""),
                 "failure_semantics": (contract or {}).get(
                     "failure_semantics", LEGAL_FAILURE),
                 "fallback": (contract or {}).get("fallback", "ask_human"),
                 "params": copy.deepcopy(call_params)}
        self._entries.append(copy.deepcopy(entry))
        if self._path is not None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False,
                                    sort_keys=True) + "\n")
        return dict(entry)

    def entries(self) -> list[dict[str, Any]]:
        return [dict(e) for e in self._entries]
