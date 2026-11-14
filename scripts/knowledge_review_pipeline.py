# -*- coding: utf-8 -*-
"""PRD-433/T2（trend issue #2085 的 T2 环节）：知识条目评审流水线 最小实现。

按 T1 设计（docs/plans/2026-11-14-prd-433-knowledge-review-pipeline-design.md）§4 落地：
  - 三条确定性规则（规则先行 R2，本地纯函数可复算零外呼）：
    R-NUM-RECALC 数字复算（stated≠recomputed）/ R-TERM-DRIFT 口径检查
    （命中旧口径词表）/ R-REF-MISSING 引用核对（悬空 [ref:*]）；
  - judge_fn 注入式逐候选判 confirmed/false_positive（模型后判 R2，
    只判候选不自由发挥）；候选未全判 → REVIEW_INCOMPLETE 拒绝落账（R4）；
  - run_pipeline(draft, judge_fn)：候选→判定→verdict（任一 confirmed 即
    blocked，R1/T1 §7①）；三件套落 ReviewPipelineLedger（JSONL append-only
    路径注入 R3）；outlet：个人 Wiki 出口包装——只放行 pass 草稿（R1）。
零网络零子进程；示例全虚构占位。
测试：tests/test_knowledge_review_pipeline.py
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from collections.abc import Callable
from typing import Any

SCHEMA = "knowledge-review-pipeline/v1"
VERDICTS = ("pass", "blocked")
JUDGE_VERDICTS = ("confirmed", "false_positive")
RULE_IDS = ("R-NUM-RECALC", "R-TERM-DRIFT", "R-REF-MISSING")
OLD_TERMS = ("旧口径（占位）", "老口径（占位）")
ERROR_CODES = ("REVIEW_INCOMPLETE", "REVIEW_VERDICT_MISMATCH")


class PipelineError(ValueError):
    """评审流水线违规——显形拒绝。"""


def _refused(code: str, detail: str) -> dict[str, Any]:
    return {"schema": SCHEMA, "refused": code, "detail": detail,
            "verdict": None}


def scan_candidates(draft: dict[str, Any]) -> list[dict[str, Any]]:
    """规则先行（R2）：三条确定性规则扫全稿，候选带逐行定位。"""
    candidates: list[dict[str, Any]] = []
    for ln in draft.get("lines") or []:
        no, text, kind = ln.get("no"), str(ln.get("text", "")), ln.get("kind")
        if kind == "number" and isinstance(ln.get("num"), dict):
            num = ln["num"]
            if num.get("stated") != num.get("recomputed"):
                candidates.append({"rule_id": "R-NUM-RECALC", "line": no,
                                   "excerpt": text,
                                   "detail": f"stated={num.get('stated')!r} "
                                             f"recomputed={num.get('recomputed')!r}"})
        for term in OLD_TERMS:
            if term in text:
                candidates.append({"rule_id": "R-TERM-DRIFT", "line": no,
                                   "excerpt": text,
                                   "detail": f"命中旧口径词 {term!r}"})
        if kind == "reference":
            for ref in re.findall(r"\[ref:([^\]]+)\]", text):
                if ref not in (draft.get("references") or []):
                    candidates.append({"rule_id": "R-REF-MISSING", "line": no,
                                       "excerpt": text,
                                       "detail": f"悬空引用 [ref:{ref}]"})
    return candidates


def run_pipeline(draft: dict[str, Any],
                 judge_fn: Callable[[list[dict[str, Any]]], list[dict[str, Any]]],
                 *, at: str = "") -> dict[str, Any]:
    """规则先扫 → judge_fn 逐候选判 → verdict；未全判拒绝（R4）。"""
    if not callable(judge_fn):
        return _refused("REVIEW_INCOMPLETE", "judge_fn 未注入")
    candidates = scan_candidates(draft)
    raw = judge_fn(copy.deepcopy(candidates)) or []
    judged: dict[tuple, dict[str, Any]] = {}
    for j in raw:
        key = (str(j.get("rule_id")), j.get("line"))
        if key not in {(str(c["rule_id"]), c["line"]) for c in candidates}:
            return _refused("REVIEW_INCOMPLETE",
                            f"判定含未知候选 {key}——judge 只判规则命中项")
        if j.get("verdict") not in JUDGE_VERDICTS:
            return _refused("REVIEW_INCOMPLETE",
                            f"verdict {j.get('verdict')!r} 词表外")
        judged[key] = dict(j, note=str(j.get("note", "")))
    missing = [(str(c["rule_id"]), c["line"]) for c in candidates
               if (str(c["rule_id"]), c["line"]) not in judged]
    if missing:
        return _refused("REVIEW_INCOMPLETE",
                        f"候选未全判：{missing}（R4 不漏判）")
    judgments = [judged[(str(c["rule_id"]), c["line"])]
                 for c in candidates]
    confirmed = [j for j in judgments if j["verdict"] == "confirmed"]
    verdict = "blocked" if confirmed else "pass"     # T1 §7①：无灰度
    return {"schema": SCHEMA, "review_id": f"rv-{draft.get('draft_id', '')}",
            "draft_id": str(draft.get("draft_id", "")),
            "candidates": candidates, "judgments": judgments,
            "verdict": verdict, "confirmed_count": len(confirmed),
            "at": at}


class ReviewPipelineLedger:
    """评审结论账本：JSONL append-only（R3），缺件拒绝入账。"""

    _REQUIRED = ("review_id", "draft_id", "candidates", "judgments",
                 "verdict")

    def __init__(self, path: str | Path | None = None) -> None:
        self._records: list[dict[str, Any]] = []
        self._path = Path(path) if path else None

    def record(self, out: dict[str, Any]) -> dict[str, Any]:
        if out.get("refused"):
            raise PipelineError(f"{out['refused']}：{out['detail']}")
        rec = dict(out)
        missing = [k for k in self._REQUIRED
                   if k not in rec or rec.get(k) in (None, "")]
        if missing:
            raise PipelineError(f"REVIEW_INCOMPLETE：账目缺 {missing}")
        if rec["verdict"] not in VERDICTS:
            raise PipelineError("REVIEW_INCOMPLETE：verdict 词表外")
        confirmed = [j for j in rec["judgments"]
                     if j.get("verdict") == "confirmed"]
        if (rec["verdict"] == "blocked") != bool(confirmed):
            raise PipelineError("REVIEW_VERDICT_MISMATCH：verdict 与 confirmed "
                                "判定不一致（R4 双向对账）")
        self._records.append(copy.deepcopy(rec))
        if self._path is not None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False,
                                    sort_keys=True) + "\n")
        return dict(rec)

    def entries(self) -> list[dict[str, Any]]:
        return [dict(r) for r in self._records]

    def latest_for(self, draft_id: str) -> dict[str, Any] | None:
        found = [r for r in self._records if r["draft_id"] == draft_id]
        return dict(found[-1]) if found else None

    def outlet(self, drafts: list[dict[str, Any]]) -> dict[str, Any]:
        """个人 Wiki 出口包装（R1）：只放行 pass 草稿，blocked 拦下留痕。"""
        state = {r["draft_id"]: r["verdict"] for r in self._records}
        passed, blocked = [], []
        for d in drafts or []:
            did = str(d.get("draft_id"))
            if state.get(did) == "pass":
                passed.append(copy.deepcopy(d))
            else:
                blocked.append(dict(copy.deepcopy(d),
                                    verdict=state.get(did)))
        return {"schema": SCHEMA, "passed": passed, "blocked": blocked,
                "blocked_count": len(blocked)}
