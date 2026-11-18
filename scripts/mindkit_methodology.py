# -*- coding: utf-8 -*-
"""PRD-539/T2（trend issue #2614 的 T2 环节）：mind-kit 知识方法论包 方法论包最小实现。

按 T1 设计（docs/plans/2026-11-19-prd-539-mindkit-methodology-design.md）§1/§3 落地：方法论包四件套落账——
  - WORKFLOW_STEPS：5 步标准做法（封闭词表，跳步/乱步/多步
    在 check_step_sequence 拦下）；
  - SKILLSET：知识 skill 集（收口本仓既有技能，不新增形态）；
  - COMMAND：`/capture` 命令入口（--step 可逐步驱动）；
  - PatternLedger：模式库 JSONL append-only（路径注入），条目必带
    pattern / source_case / evidence / caliber_version 四件，缺一拒绝
    入账；首份模式条目取自本仓真实产物（来源见条目 evidence）。
  - render_pack_md：方法论包 Markdown 渲染（两遍逐字节一致）。
零网络零子进程；示例全虚构占位。
测试：tests/test_mindkit_methodology.py
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

METHODOLOGY_SCHEMA = "mindkit-methodology/v1"
METHOD_DOMAIN = "mind-kit 知识方法论包"
METHOD_COMMAND = "/capture"
WORKFLOW_STEPS = ["采来源", "抽知识", "复核", "入库", "复用"]
SKILLSET_NAME = "知识 skill 集"
PATTERN_REQUIRED = ("pattern", "source_case", "evidence", "caliber_version")


class MethodologyError(ValueError):
    """方法论包违规——显形拒绝。"""


def check_step_sequence(steps: list[str] | None) -> dict[str, Any]:
    """workflow 步骤序列校验：实际执行序列必须是 workflow 的严格前缀
    （进行中合法）或全序列（完成）；跳步/乱步/多步 → STEP_INVALID。"""
    if not isinstance(steps, list) or any(
            not isinstance(s, str) or not s for s in steps):
        return {"ok": False, "reason": "STEP_INVALID",
                "detail": "步骤序列非字符串列表"}
    n = len(steps)
    if n > len(WORKFLOW_STEPS):
        return {"ok": False, "reason": "STEP_INVALID",
                "detail": f"步骤数 {n} 超出 workflow {len(WORKFLOW_STEPS)} 步"
                          f"（多步）"}
    for i, s in enumerate(steps):
        if s != WORKFLOW_STEPS[i]:
            return {"ok": False, "reason": "STEP_INVALID",
                    "detail": f"第 {i + 1} 步应为 {WORKFLOW_STEPS[i]!r}，"
                              f"实际 {s!r}（乱步/跳步）"}
    return {"ok": True, "reason": "ok",
            "detail": "完成" if n == len(WORKFLOW_STEPS) else "进行中"}


class PatternLedger:
    """模式库账本：JSONL append-only（路径注入），条目四件缺一拒绝入账。

    只追加、不改历史条目；entries() 返回深拷贝，改返回结果不污染账本。
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self._records: list[dict[str, Any]] = []
        self._path = Path(path) if path else None

    def record(self, entry: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(entry, dict):
            raise MethodologyError("PATTERN_INVALID：条目非对象")
        missing = [k for k in PATTERN_REQUIRED
                   if k not in entry
                   or not isinstance(entry.get(k), str)
                   or not entry.get(k).strip()]
        if missing:
            raise MethodologyError(
                f"PATTERN_INCOMPLETE：模式条目缺 {missing}——"
                f"每条必须带 pattern/source_case/evidence/caliber_version")
        rec = {"schema": METHODOLOGY_SCHEMA, **copy.deepcopy(entry)}
        self._records.append(copy.deepcopy(rec))
        if self._path is not None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False,
                                    sort_keys=True) + "\n")
        return dict(rec)

    def entries(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._records)


def render_pack_md() -> str:
    """方法论包 Markdown 渲染（四件套全展示；两遍逐字节一致）。"""
    lines = [
        f"# {METHOD_DOMAIN}方法论包（mindkit-methodology/v1）",
        "",
        f"- 命令入口：`{METHOD_COMMAND}`（按 workflow 顺序驱动，--step 可逐步执行）",
        f"- skill 集：{SKILLSET_NAME}（收口本仓既有技能，不新增形态）",
        "",
        "## workflow（5 步标准做法）",
        "",
        "| # | 步骤 | 完成判据 |",
        "|---|---|---|",
    ]
    for i, s in enumerate(WORKFLOW_STEPS, 1):
        lines.append(f"| {i} | {s} | {s}判据可验证（字段见包校验） |")
    lines += [
        "",
        "## 模式库",
        "",
        "- JSONL append-only：docs/methodology/mindkit-patterns.jsonl",
        "- 条目四件：pattern / source_case / evidence / caliber_version（缺一在"
        " T3 校验拦下）；首份条目取自本仓真实产物。",
        "",
        "## 红线",
        "",
        "- 无方法论包的技能不成套、不进上游审批（T3 校验拦截）。",
        "- 方法论包不代行审批：只定做法，内容对不对仍由评审流水线与监督回路审。",
        "- 模式库只追加、不改历史条目。",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="方法论包渲染（四件套落账）")
    parser.add_argument("--pack", required=True, help="方法论包 md 输出路径")
    args = parser.parse_args(argv)
    out = Path(args.pack)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_pack_md(), encoding="utf-8")
    print(json.dumps({"workflow_steps": len(WORKFLOW_STEPS),
                      "command": METHOD_COMMAND,
                      "pack": str(out)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
