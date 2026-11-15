# -*- coding: utf-8 -*-
"""PRD-456/T2（trend issue #2201 的 T2 环节）：知识监督台 最小实现。

按 T1 设计（docs/plans/2026-11-15-prd-456-knowledge-supervision-bench-design.md）§3-§4 落地：
  - 三件套数据模型：进度 progress（出炉步骤 + 状态 + 时间戳）/
    批注 annotations（锚点 + 内容 + 类型 + 作者 + 状态）/
    发回反馈 feedback_rounds（关联批注 + 发回指令 + 回版对照），
    同一知识多版本之间批注不丢失；
  - 三个接入点：supervise（整理开始 / 整理完成，建进度 pending）/
    发回（feedback 一键打包批注，verdict=returned）/
    revise（改完回来，版本号 +1，旧批注带到新版上对照，verdict 回 pending）；
  - supervise(..., approve=True)：只有无未处理批注才能点头，verdict=approved；
    有未处理批注却点头 → SUPERVISION_VERDICT_MISMATCH 拒绝；
  - SupervisionLedger：三件套落 JSONL append-only 账本（路径注入），
    缺件 SUPERVISION_INCOMPLETE 拒绝入账；
  - outlet：个人 Wiki 出口包装——只放行 approved，pending/returned/
    无记录一律拦下留痕（未点头的知识不进个人 Wiki）。
零网络零子进程；示例全虚构占位。
测试：tests/test_knowledge_supervision_bench.py
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

SCHEMA = "knowledge-supervision-bench/v1"
VERDICTS = ("approved", "returned", "pending")
PROGRESS_STEPS = ("drafted", "returned", "revised", "approved")
ANNOTATION_TYPES = ("换来源", "补标签", "疑问", "通过")
ANNOTATION_STATUSES = ("待处理", "已采纳", "已驳回")
FEEDBACK_KINDS = ("换来源", "补标签", "只改指定处")
ERROR_CODES = ("SUPERVISION_INCOMPLETE", "SUPERVISION_VERDICT_MISMATCH")


class SupervisionError(ValueError):
    """监督台违规——显形拒绝。"""


def _refused(code: str, detail: str) -> dict[str, Any]:
    return {"schema": SCHEMA, "refused": code, "detail": detail,
            "verdict": None}


def _unresolved(annotations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """未处理批注：状态待处理且类型不是通过。"""
    return [a for a in annotations
            if a.get("status") == "待处理" and a.get("type") != "通过"]


def _norm_annotations(raw: Any) -> tuple[list[dict[str, Any]], str | None]:
    """批注归一化：缺 type 默认为疑问；缺 text / 词表外 / 状态词表外 → 拒绝原因。"""
    annotations: list[dict[str, Any]] = []
    for i, a in enumerate(raw or []):
        if not isinstance(a, dict):
            return [], f"批注 #{i + 1} 非对象"
        text = str(a.get("text") or "").strip()
        if not text:
            return [], f"批注 #{i + 1} 缺正文"
        typ = a.get("type") or "疑问"
        if typ not in ANNOTATION_TYPES:
            return [], f"批注类型 {typ!r} 词表外"
        status = a.get("status") or "待处理"
        if status not in ANNOTATION_STATUSES:
            return [], f"批注状态 {status!r} 词表外"
        annotations.append({
            "annotation_id": str(a.get("annotation_id") or f"a-{i + 1:03d}"),
            "anchor": str(a.get("anchor") or ""),
            "text": text, "type": typ,
            "author": str(a.get("author") or "reviewer-placeholder"),
            "at": str(a.get("at") or ""),
            "status": status})
    return annotations, None


def supervise(item: dict[str, Any], annotations: Any = None,
              feedback: dict[str, Any] | None = None, *,
              approve: bool = False, at: str = "") -> dict[str, Any]:
    """整理开始 / 整理完成：建一条监督记录（pending 起步）。

    annotations：批注列表；feedback：{kind, text, annotation_ids?}，一次发回
    可带多条批注（annotation_ids 省略即带全部）；approve=True 为点头。
    发回与点头不能同一次；点头时有未处理批注 → 拒绝。
    """
    if not isinstance(item, dict):
        return _refused("SUPERVISION_INCOMPLETE", "知识非对象")
    item_id = str(item.get("knowledge_id") or "")
    if not item_id:
        return _refused("SUPERVISION_INCOMPLETE", "缺少knowledge_id")
    version = item.get("version", 1)
    if not isinstance(version, int) or isinstance(version, bool) \
            or version < 1:
        return _refused("SUPERVISION_INCOMPLETE", "version 须为 ≥1 的整数")
    normed, err = _norm_annotations(annotations)
    if err is not None:
        return _refused("SUPERVISION_INCOMPLETE", err)
    rounds: list[dict[str, Any]] = []
    if feedback is not None:
        if not isinstance(feedback, dict):
            return _refused("SUPERVISION_INCOMPLETE", "feedback 非对象")
        kind = feedback.get("kind")
        if kind not in FEEDBACK_KINDS:
            return _refused("SUPERVISION_INCOMPLETE",
                            f"发回指令 {kind!r} 词表外")
        text = str(feedback.get("text") or "").strip()
        if not text:
            return _refused("SUPERVISION_INCOMPLETE", "发回缺正文")
        ids = [a["annotation_id"] for a in normed]
        wanted = feedback.get("annotation_ids") or ids
        unknown = [x for x in wanted if x not in ids]
        if unknown:
            return _refused("SUPERVISION_INCOMPLETE",
                            f"发回引用了未知批注 {unknown}")
        rounds.append({"round": 1, "kind": kind, "feedback": text,
                       "annotation_ids": list(wanted),
                       "revised_knowledge_id": None})
    if approve and feedback is not None:
        return _refused("SUPERVISION_VERDICT_MISMATCH",
                        "发回与点头不能同一次")
    if approve and _unresolved(normed):
        return _refused("SUPERVISION_VERDICT_MISMATCH",
                        "有未处理批注却点头")
    verdict = "approved" if approve else ("returned" if rounds else "pending")
    progress = [{"step": "drafted", "at": at}]
    if rounds:
        progress.append({"step": "returned", "at": at})
    if verdict == "approved":
        progress.append({"step": "approved", "at": at})
    return {"schema": SCHEMA, "supervision_id": f"sv-{item_id}",
            "knowledge": copy.deepcopy(item),
            "knowledge_id": item_id, "version": version,
            "progress": progress, "annotations": normed,
            "feedback_rounds": rounds, "verdict": verdict, "at": at}


def revise(record: dict[str, Any], revised_item: dict[str, Any], *,
           at: str = "") -> dict[str, Any]:
    """改完回来：只有 verdict=returned 的记录能接回新版。

    版本号 +1，progress 追加 revised，旧批注原样带到新版上对照（未处理的
    继续挂着），上一轮发回记下回版对照；verdict 回 pending 待复核。
    """
    if not isinstance(record, dict) or record.get("refused"):
        return _refused("SUPERVISION_INCOMPLETE", "监督记录无效")
    if record.get("verdict") != "returned":
        return _refused("SUPERVISION_INCOMPLETE",
                        "只有已发回的记录能改完回来")
    if not isinstance(revised_item, dict):
        return _refused("SUPERVISION_INCOMPLETE", "知识非对象")
    item_id = str(revised_item.get("knowledge_id") or "")
    if item_id != record.get("knowledge_id"):
        return _refused("SUPERVISION_INCOMPLETE",
                        "知识标识与原记录不一致")
    version = revised_item.get("version", record["version"] + 1)
    if not isinstance(version, int) or isinstance(version, bool) \
            or version != record["version"] + 1:
        return _refused("SUPERVISION_INCOMPLETE",
                        "回版 version 须为原版本 +1")
    rounds = copy.deepcopy(record.get("feedback_rounds") or [])
    if rounds:
        rounds[-1]["revised_knowledge_id"] = item_id
    progress = copy.deepcopy(record.get("progress") or [])
    progress.append({"step": "revised", "at": at})
    return {"schema": SCHEMA,
            "supervision_id": record["supervision_id"],
            "knowledge": copy.deepcopy(revised_item),
            "knowledge_id": item_id, "version": version,
            "progress": progress,
            "annotations": copy.deepcopy(record.get("annotations") or []),
            "feedback_rounds": rounds, "verdict": "pending", "at": at}


class SupervisionLedger:
    """监督结论账本：JSONL append-only，缺件拒绝入账。"""

    _REQUIRED = ("supervision_id", "knowledge_id", "version", "progress",
                 "annotations", "feedback_rounds", "verdict")

    def __init__(self, path: str | Path | None = None) -> None:
        self._records: list[dict[str, Any]] = []
        self._path = Path(path) if path else None

    def record(self, out: dict[str, Any]) -> dict[str, Any]:
        if out.get("refused"):
            raise SupervisionError(f"{out['refused']}：{out['detail']}")
        rec = dict(out)
        missing = [k for k in self._REQUIRED
                   if k not in rec or rec.get(k) in (None, "")]
        if missing:
            raise SupervisionError(f"SUPERVISION_INCOMPLETE：账目缺 {missing}")
        if rec["verdict"] not in VERDICTS:
            raise SupervisionError("SUPERVISION_INCOMPLETE：verdict 词表外")
        if rec["verdict"] == "approved" and _unresolved(rec["annotations"]):
            raise SupervisionError("SUPERVISION_VERDICT_MISMATCH：声称 approved "
                                   "却有未处理批注")
        if rec["verdict"] == "returned" and not rec["feedback_rounds"]:
            raise SupervisionError("SUPERVISION_VERDICT_MISMATCH：verdict 为 "
                                   "returned 却无发回轮次")
        if rec["verdict"] == "pending" and any(
                s.get("step") == "approved" for s in rec["progress"]):
            raise SupervisionError("SUPERVISION_VERDICT_MISMATCH：pending 记录"
                                   "含 approved 进度")
        self._records.append(copy.deepcopy(rec))
        if self._path is not None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False,
                                    sort_keys=True) + "\n")
        return dict(rec)

    def entries(self) -> list[dict[str, Any]]:
        return [dict(r) for r in self._records]

    def latest_for(self, item_id: str) -> dict[str, Any] | None:
        found = [r for r in self._records
                 if r["knowledge_id"] == item_id]
        return dict(found[-1]) if found else None

    def outlet(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        """个人 Wiki 出口包装：只放行 approved，余者拦下留痕。"""
        state = {r["knowledge_id"]: r["verdict"] for r in self._records}
        passed, blocked = [], []
        for it in items or []:
            iid = str(it.get("knowledge_id"))
            if state.get(iid) == "approved":
                passed.append(copy.deepcopy(it))
            else:
                blocked.append(dict(copy.deepcopy(it),
                                    verdict=state.get(iid)))
        return {"schema": SCHEMA, "passed": passed, "blocked": blocked,
                "blocked_count": len(blocked)}
