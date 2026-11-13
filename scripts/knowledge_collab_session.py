 # -*- coding: utf-8 -*-
"""PRD-410/T2（trend issue #1970 的 T2 环节）：知识共建会话 最小实现。

按 T1 设计（docs/plans/2026-11-13-prd-410-knowledge-collab-session-design.md）§4 落地：
  - propose/accept/reject：会话事件原语——每事件带 author+at（署名 R2）；
    缺一 SESSION_INCOMPLETE 拒绝入账；状态机 proposed→accepted/rejected
    单向（R4），重复接受/unknown id/rejected 再接受 SESSION_STATE_CONFLICT；
  - CollabSessionLedger：事件流 JSONL append-only 落库（路径注入 R3）；
    statuses()/replay() 对同一事件流确定性重建状态（两遍一致）；
  - outlet：个人 Wiki 出口包装——只放行 accepted 改动（R1），未接受拦下留痕。
零网络零子进程（同屏=对同一份日志的回放视图）；示例全虚构占位。
测试：tests/test_knowledge_collab_session.py
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

SESSION_SCHEMA = "knowledge-collab-session/v1"
EVENTS = ("propose", "accept", "reject")
STATUSES = ("proposed", "accepted", "rejected")
ERROR_CODES = ("SESSION_INCOMPLETE", "SESSION_STATE_CONFLICT")


class SessionError(ValueError):
    """会话违规——显形拒绝。"""


def _refused(code: str, detail: str) -> dict[str, Any]:
    return {"schema": SESSION_SCHEMA, "refused": code, "detail": detail,
            "event": None}


def _missing(*vals: Any) -> bool:
    return any(v in (None, "") for v in vals)


def propose(entry_id: str, kind: str, author: str, at: str,
            payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """提出改动（带署名）：author/at/entry_id/kind 缺一拒绝（R2）。"""
    if _missing(entry_id, kind, author, at):
        return _refused("SESSION_INCOMPLETE",
                        f"署名缺一：entry_id/kind/author/at="
                        f"{entry_id!r}/{kind!r}/{author!r}/{at!r}")
    return {"schema": SESSION_SCHEMA, "event": "propose",
            "entry_id": str(entry_id), "kind": kind, "author": author,
            "at": at, "payload": copy.deepcopy(payload or {}),
            "status": "proposed"}


def accept(entry_id: str, by: str, at: str) -> dict[str, Any]:
    if _missing(entry_id, by, at):
        return _refused("SESSION_INCOMPLETE",
                        f"署名缺一：entry_id/by/at={entry_id!r}/{by!r}/{at!r}")
    return {"schema": SESSION_SCHEMA, "event": "accept",
            "entry_id": str(entry_id), "kind": "", "author": by, "at": at,
            "payload": {}, "status": "accepted"}


def reject(entry_id: str, by: str, at: str,
           reason: str = "") -> dict[str, Any]:
    if _missing(entry_id, by, at):
        return _refused("SESSION_INCOMPLETE",
                        f"署名缺一：entry_id/by/at={entry_id!r}/{by!r}/{at!r}")
    return {"schema": SESSION_SCHEMA, "event": "reject",
            "entry_id": str(entry_id), "kind": "", "author": by, "at": at,
            "payload": {"reason": reason}, "status": "rejected"}


def replay(events: list[dict[str, Any]]) -> dict[str, str]:
    """确定性回放：对同一事件流两遍重建状态逐条一致（R3）。"""
    state: dict[str, str] = {}
    for ev in events or []:
        eid = str(ev.get("entry_id"))
        if ev.get("event") == "propose":
            state[eid] = "proposed"
        elif ev.get("event") == "accept":
            if state.get(eid) != "proposed":
                raise SessionError(
                    f"SESSION_STATE_CONFLICT：{eid} 当前 {state.get(eid)!r}"
                    " 不可接受——状态机单向")
            state[eid] = "accepted"
        elif ev.get("event") == "reject":
            if state.get(eid) != "proposed":
                raise SessionError(
                    f"SESSION_STATE_CONFLICT：{eid} 当前 {state.get(eid)!r}"
                    " 不可拒绝——状态机单向")
            state[eid] = "rejected"
        else:
            raise SessionError(
                f"SESSION_INCOMPLETE：event {ev.get('event')!r} 词表外")
    return state


class CollabSessionLedger:
    """协同会话账本：事件流 JSONL append-only（R3），状态由 replay 派生。"""

    def __init__(self, path: str | Path | None = None) -> None:
        self._events: list[dict[str, Any]] = []
        self._path = Path(path) if path else None

    def _record(self, ev: dict[str, Any]) -> dict[str, Any]:
        if ev.get("refused"):
            raise SessionError(f"{ev['refused']}：{ev['detail']}")
        ev = dict(ev, seq=len(self._events) + 1)
        replay(self._events + [ev])   # 状态机校验（R4），违规则整事件拒绝
        self._events.append(copy.deepcopy(ev))
        if self._path is not None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(ev, ensure_ascii=False,
                                    sort_keys=True) + "\n")
        return dict(ev)

    def propose_change(self, entry_id: str, kind: str, author: str, at: str,
                       payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._record(propose(entry_id, kind, author, at, payload))

    def accept_change(self, entry_id: str, by: str, at: str) -> dict[str, Any]:
        return self._record(accept(entry_id, by, at))

    def reject_change(self, entry_id: str, by: str, at: str,
                      reason: str = "") -> dict[str, Any]:
        return self._record(reject(entry_id, by, at, reason))

    def events(self) -> list[dict[str, Any]]:
        return [dict(e) for e in self._events]

    def statuses(self) -> dict[str, str]:
        return replay(self._events)

    def outlet(self, entries: list[dict[str, Any]]) -> dict[str, Any]:
        """个人 Wiki 出口包装（R1）：只放行 accepted 改动，未接受拦下留痕。"""
        state = self.statuses()
        accepted, blocked = [], []
        for e in entries or []:
            eid = str(e.get("entry_id"))
            if state.get(eid) == "accepted":
                accepted.append(copy.deepcopy(e))
            else:
                blocked.append(dict(copy.deepcopy(e), status=state.get(eid)))
        return {"schema": SESSION_SCHEMA, "accepted": accepted,
                "blocked": blocked, "blocked_count": len(blocked)}

    def replay_from_log(self) -> dict[str, str]:
        return replay(self._events)
