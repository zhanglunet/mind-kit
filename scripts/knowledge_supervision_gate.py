# -*- coding: utf-8 -*-
"""PRD-456/T3（trend issue #2202 的 T3 环节）：知识监督台监督回路闸门。

按 T1 设计（docs/plans/2026-11-15-prd-456-knowledge-supervision-bench-design.md）
§5/§10 落地——关口规则写成可测试的断言，闸门立在 T2 的
``SupervisionLedger`` 与个人 Wiki 出口之间，只做守门，不改 T2 的
三件套数据模型与三个接入点：

  - 出口拦截（SUPERVISION_OUTLET_BYPASS）：出口收到无监督记录的知识
    → 拦截并告警（记入闸门审计账本的 bypass_alerts），不放行；
  - verdict 双向对账（SUPERVISION_VERDICT_MISMATCH）：声称 approved
    却有未处理批注，或无带时间戳的点头进度 → 显形拒绝；
  - 一票否决：任一断言失败即整条拦下，不存在"带警告放行"；一批里
    只要有一条被拦下，整批标记 vetoed，下游不得按整批入库；
  - 账本漂移（LEDGER_DRIFT）：闸门钉住账本首条的摘要；首条被删/改
    → 全批拒绝；
  - 旧点头不放行新版（VERSION_MISMATCH）：监督记录版本与待审知识
    版本不一致 → 拦下，改完回来须重新点头；
  - 无默认通过：无记录、缺件、超时未裁决一律拦下。

审计：每一次闸门裁决都 append-only 落账（GateAudit，路径注入），
批注与反馈留痕口径与 T2 一致。零网络零子进程；示例全虚构占位。
测试：tests/test_knowledge_supervision_gate.py
借鉴只借形态：plannotator（Apache-2.0）、ag-ui（MIT）——本模块为原创
代码，未复用其代码；LoopForge（无 LICENSE）只借"人工批准门"形态，
零代码零文本复用。
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

GATE_SCHEMA = "knowledge-supervision-gate/v1"
GATE_CODES = ("SUPERVISION_INCOMPLETE", "SUPERVISION_VERDICT_MISMATCH",
              "SUPERVISION_OUTLET_BYPASS", "LEDGER_DRIFT")
GATE_REASONS = ("NOT_APPROVED", "VERSION_MISMATCH") + GATE_CODES
DECISIONS = ("pass", "block")


class GateError(ValueError):
    """闸门违规——显形拒绝。"""


def _anchor(record: dict[str, Any]) -> str:
    """账本首条摘要：规范 JSON 的 SHA-256。"""
    canonical = json.dumps(record, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _unresolved(annotations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """未处理批注：状态待处理且类型不是通过（与 T2 口径一致）。"""
    return [a for a in annotations
            if a.get("status") == "待处理" and a.get("type") != "通过"]


class SupervisionGate:
    """知识监督台出口闸门：守在账本与个人 Wiki 之间。

    ledger 为 T2 的 SupervisionLedger（只读使用：entries/latest_for）。
    构造时钉住账本首条摘要；账本为空时在首次裁决前钉住首条。
    """

    def __init__(self, ledger: Any, path: str | Path | None = None) -> None:
        self._ledger = ledger
        self._decisions: list[dict[str, Any]] = []
        self._path = Path(path) if path else None
        self._anchor: str | None = None
        self._pin_anchor()

    def _pin_anchor(self) -> None:
        entries = self._ledger.entries()
        if entries and self._anchor is None:
            self._anchor = _anchor(entries[0])

    def _drift(self) -> bool:
        entries = self._ledger.entries()
        if self._anchor is None:
            self._pin_anchor()
            return False
        if not entries:
            return True
        return _anchor(entries[0]) != self._anchor

    def _audit(self, decision: dict[str, Any]) -> None:
        stored = copy.deepcopy(decision)
        self._decisions.append(stored)
        if self._path is not None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(stored, ensure_ascii=False,
                                    sort_keys=True) + "\n")

    def gate(self, item: dict[str, Any], *, at: str = "") -> dict[str, Any]:
        """对一条知识做一次闸门裁决：全过才 pass，否则 block。"""
        item_id = ""
        version = None
        if isinstance(item, dict):
            item_id = str(item.get("knowledge_id") or "")
            version = item.get("version")
        decision: dict[str, Any] = {
            "schema": GATE_SCHEMA, "decision": "block", "reason": None,
            "detail": "", "knowledge_id": item_id or None,
            "version": version, "at": at}

        def _block(reason: str, detail: str) -> dict[str, Any]:
            decision.update({"reason": reason, "detail": detail})
            self._audit(decision)
            return dict(decision)

        if self._drift():
            return _block("LEDGER_DRIFT", "账本首条被删/改")
        if not isinstance(item, dict) or not item_id:
            return _block("SUPERVISION_INCOMPLETE",
                          "知识非对象或缺少 knowledge_id")
        if not isinstance(version, int) or isinstance(version, bool) \
                or version < 1:
            return _block("SUPERVISION_INCOMPLETE",
                          "version 须为 ≥1 的整数")
        record = self._ledger.latest_for(item_id)
        if record is None:
            return _block("SUPERVISION_OUTLET_BYPASS",
                          "出口收到无监督记录的知识")
        if record.get("version") != version:
            return _block(
                "VERSION_MISMATCH",
                f"监督记录版本 {record.get('version')} 与待审版本"
                f" {version} 不一致（旧点头不放行新版）")
        if record.get("verdict") != "approved":
            return _block("NOT_APPROVED",
                          f"verdict 为 {record.get('verdict')}，未点头")
        if _unresolved(record.get("annotations") or []):
            return _block("SUPERVISION_VERDICT_MISMATCH",
                          "声称 approved 却有未处理批注")
        approved_steps = [s for s in (record.get("progress") or [])
                          if s.get("step") == "approved"]
        if not approved_steps or not any(
                str(s.get("at") or "").strip() for s in approved_steps):
            return _block("SUPERVISION_VERDICT_MISMATCH",
                          "声称 approved 却无带时间戳的点头进度")
        decision.update({"decision": "pass", "reason": None,
                         "detail": "已点头且断言全过"})
        self._audit(decision)
        return dict(decision)

    def gate_outlet(self, items: list[dict[str, Any]],
                    *, at: str = "") -> dict[str, Any]:
        """个人 Wiki 出口：逐条过闸；任一拦下即整批 vetoed。"""
        passed, blocked, alerts = [], [], []
        for item in items or []:
            verdict = self.gate(item, at=at)
            if verdict["decision"] == "pass":
                passed.append(copy.deepcopy(item))
            else:
                blocked.append(dict(
                    copy.deepcopy(item) if isinstance(item, dict)
                    else {"item": item},
                    gate_reason=verdict["reason"],
                    gate_detail=verdict.get("detail", "")))
                if verdict["reason"] == "SUPERVISION_OUTLET_BYPASS":
                    alerts.append(dict(verdict))
        return {"schema": GATE_SCHEMA, "passed": passed, "blocked": blocked,
                "blocked_count": len(blocked), "bypass_alerts": alerts,
                "vetoed": bool(blocked)}

    def decisions(self) -> list[dict[str, Any]]:
        return [dict(d) for d in self._decisions]

    def alerts(self) -> list[dict[str, Any]]:
        return [dict(d) for d in self._decisions
                if d.get("reason") == "SUPERVISION_OUTLET_BYPASS"]

    def decisions_for(self, item_id: str) -> list[dict[str, Any]]:
        return [dict(d) for d in self._decisions
                if d.get("knowledge_id") == item_id]
