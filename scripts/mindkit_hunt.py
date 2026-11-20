# -*- coding: utf-8 -*-
"""PRD-585/T2（trend issue #2936 的 T2 环节）：mind-kit 知识产物红队巡检巡检最小实现。

按 T1 设计（docs/plans/2026-11-20-prd-585-mindkit-hunting-design.md）落地红队巡检：
  - SUSPECTS：疑点封闭词表（4 项攻击面，落账不猜）；
  - reproduce：复现器——在产物上跑该疑点的攻击面检查，复现/不复现
    二值返回（无复现证据的 finding 不入账）；
  - run_hunt：全疑点巡检跑一遍 → 巡检报告（有发现/无可复现发现，
    结论封闭）；
  - FindingLedger：FINDING JSONL append-only 留痕（finding/repro/
    evidence/found_at 四件缺一拒绝入账）；
  - CLI：main() --artifact --report（agent-native 入口）。
零网络零子进程；示例全虚构占位。
测试：tests/test_mindkit_hunt.py
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

HUNT_SCHEMA = "mindkit-hunt/v1"
SUSPECTS = ('S1_过期条目', 'S2_矛盾条目', 'S3_孤证条目', 'S4_环状引用')
REPRO_VERDICTS = ("复现", "不复现")
HUNT_CONCLUSIONS = ("有发现", "无可复现发现")
FINDING_REQUIRED = ("finding", "repro", "evidence", "found_at")
HUNT_TS = "2026-11-20T09:00:00Z"


class HuntError(ValueError):
    """巡检违规——显形拒绝。"""


def _tail(suspect: str) -> str:
    return suspect.split("_", 1)[1]


def reproduce(suspect: str, artifact: dict) -> dict[str, Any]:
    """复现器：在产物上跑该疑点的攻击面检查（二值返回）。"""
    text = str(artifact.get("text", ""))
    token = _tail(suspect)
    hit = token in text
    return {"suspect": suspect, "verdict": "复现" if hit else "不复现",
            "evidence": f"命中：{token}（占位）" if hit else "无命中（占位）"}


def run_hunt(artifact: dict) -> dict[str, Any]:
    """全疑点巡检跑一遍，返回巡检报告（含可入账 finding 条目）。"""
    results = [reproduce(s, artifact) for s in SUSPECTS]
    findings = []
    for r in results:
        if r["verdict"] == "复现":
            findings.append({"finding": f"{r['suspect']}：{r['evidence']}",
                             "repro": "复现", "evidence": r["evidence"],
                             "found_at": HUNT_TS})
    hunt = "有发现" if findings else "无可复现发现"
    return {"schema": HUNT_SCHEMA, "artifact": str(artifact.get("name", "")),
            "suspects": list(SUSPECTS), "results": results,
            "findings": findings, "hunt": hunt}


class FindingLedger:
    """FINDING JSONL append-only 留痕（四件缺一拒绝入账）。"""

    def __init__(self, path: str | Path | None = None) -> None:
        self._records: list[dict[str, Any]] = []
        self._path = Path(path) if path else None

    def record(self, entry: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(entry, dict):
            raise HuntError("FINDING_INVALID：条目非对象")
        missing = [k for k in FINDING_REQUIRED
                   if k not in entry or not str(entry.get(k, "")).strip()]
        if missing:
            raise HuntError(f"FINDING_INCOMPLETE：FINDING 条目缺 {missing}")
        if entry.get("repro") not in REPRO_VERDICTS:
            raise HuntError(
                f"REPRO_INVALID：repro 必须是 {REPRO_VERDICTS}（无复现证据的"
                "finding 不入账）")
        rec = {"schema": HUNT_SCHEMA, **copy.deepcopy(entry)}
        self._records.append(copy.deepcopy(rec))
        if self._path is not None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False,
                                    sort_keys=True) + "\n")
        return copy.deepcopy(rec)

    def entries(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._records)


def main(argv: list[str] | None = None) -> int:
    """agent-native CLI：--artifact <产物文本> --report <输出 json>。"""
    parser = argparse.ArgumentParser(description="红队巡检 CLI")
    parser.add_argument("--artifact", required=True, help="产物文本路径")
    parser.add_argument("--report", required=True, help="报告输出路径")
    args = parser.parse_args(argv)
    text = Path(args.artifact).read_text(encoding="utf-8")
    artifact = {"name": Path(args.artifact).stem, "text": text,
                "source_path": args.artifact}
    report = run_hunt(artifact)
    out = Path(args.report)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(json.dumps({"hunt": report["hunt"],
                      "findings": len(report["findings"])},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
