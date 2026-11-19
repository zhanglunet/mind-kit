# -*- coding: utf-8 -*-
"""PRD-562/T2（trend issue #2659 的 T2 环节）：mind-kit 知识技能准入检查准入检查最小实现。

按 T1 设计（docs/plans/2026-11-20-prd-562-mindkit-admission-design.md）落地五层准入检查：
  - L1 质量门：SKILL.md 静态完整性（frontmatter name/description/触发
    条件/约束/证据出处五项，缺项进整改）；
  - L2 安全扫描：文本规则扫描（取数越界/敏感表扫描）；
  - L3 重叠检测：与已有技能 bigram Jaccard ≥ 0.8 记疑似（不自动判死）；
  - L4 合成评测集：SKILL.md 内容生成合成题（Q/A/钉值），带钉值才有效；
  - L5 实测评估：对照数据不足判「待补测」（不编造结论）。
  - AdmissionLedger：检查结果 JSONL append-only 留痕（layer/verdict/
    evidence/checked_at 四件缺一拒绝入账）。
  - CLI：main() --check --report（agent-native 入口）。
零网络零子进程；示例全虚构占位。
测试：skill/mind-kit/scripts/test_mindkit_admission.py
"""
from __future__ import annotations

import argparse
import copy
import json
import re
from pathlib import Path
from typing import Any

ADMISSION_SCHEMA = "mindkit-admission/v1"
LAYERS = ("L1_quality", "L2_security", "L3_overlap", "L4_synth",
          "L5_live")
VERDICTS = ("过", "不过", "疑似", "待补测")
PATTERN_REQUIRED = ("layer", "verdict", "evidence", "checked_at")
OVERLAP_THRESHOLD = 0.8
STATIC_KEYS = ("name", "description", "trigger", "constraints", "evidence")


class AdmissionError(ValueError):
    """准入检查违规——显形拒绝。"""


def frontmatter(text: str) -> str:
    if text.startswith("---"):
        end = text.find("---", 3)
        if end > 0:
            return text[3:end]
    return ""


def scalar(fm: str, key: str) -> str:
    m = re.search(rf"^{key}:\s*(.+)$", fm, re.M)
    return m.group(1).strip().strip("\"'") if m else ""


def static_checks(skill: dict) -> dict[str, bool]:
    """L1 质量门：SKILL.md 静态完整性五项。"""
    fm = frontmatter(skill.get("text", ""))
    return {
        "name": bool(scalar(fm, "name")),
        "description": bool(scalar(fm, "description")),
        "trigger": ("当" in fm or "使用" in fm or "触发" in fm),
        "constraints": ("不" in fm or "约束" in fm or "限制" in fm),
        "evidence": ("来源" in fm or "出处" in fm or "reference" in fm.lower()
                     or skill.get("source_path", "") != ""),
    }


def _bigrams(text: str) -> set[str]:
    clean = re.sub(r"\s+", "", text)
    return {clean[i:i + 2] for i in range(len(clean) - 1)} if len(clean) >= 2 else {clean}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def security_scan(skill: dict) -> dict[str, Any]:
    """L2 安全扫描：取数越界/敏感表扫描。"""
    text = skill.get("text", "")
    hits = []
    for pat in ("DROP TABLE", "rm -rf /", "sudo ", "eval(", "API_KEY=",
                "password =", "密钥硬编码"):
        if pat.lower() in text.lower():
            hits.append(pat)
    return {"layer": "L2_security", "verdict": "不过" if hits else "过",
            "hits": hits}


def overlap_check(skill: dict, existing: list[dict]) -> dict[str, Any]:
    """L3 重叠检测：与已有技能 bigram Jaccard ≥ 0.8 记疑似。"""
    grams = _bigrams(skill.get("text", ""))
    suspects = []
    for ex in existing:
        sim = jaccard(grams, _bigrams(ex.get("text", "")))
        if sim >= OVERLAP_THRESHOLD:
            suspects.append({"against": ex.get("id", ""),
                              "similarity": round(sim, 3)})
    return {"layer": "L3_overlap", "verdict": "疑似" if suspects else "过",
            "suspects": suspects}


def synth_eval(skill: dict) -> dict[str, Any]:
    """L4 合成评测集：从 SKILL.md 内容生成合成题（Q/A/钉值）。"""
    text = skill.get("text", "")
    name = skill.get("name", "unknown")
    questions = []
    if text:
        questions.append({
            "q": f"{name} 的适用场景是什么？（合成题）",
            "a_expected": (scalar(frontmatter(text), "description")
                           or "见 SKILL.md description（钉值）"),
            "pin": "SKILL.md description 原文",
        })
    return {"layer": "L4_synth", "verdict": "过" if questions else "待补测",
            "questions": questions}


def live_eval(skill: dict) -> dict[str, Any]:
    """L5 实测评估：无对照数据判「待补测」（不编造结论）。"""
    return {"layer": "L5_live", "verdict": "待补测",
            "reason": "无有技能 vs 无技能对照数据（不编造）"}


def run_admission(skill: dict, existing: list[dict]) -> dict[str, Any]:
    """五层检查跑一遍，返回准入报告（含留痕条目）。"""
    l1 = static_checks(skill)
    missing = [k for k, ok in l1.items() if not ok]
    l1_verdict = "过" if not missing else "不过"
    l2 = security_scan(skill)
    l3 = overlap_check(skill, existing)
    l4 = synth_eval(skill)
    l5 = live_eval(skill)
    layers = [
        {"layer": "L1_quality", "verdict": l1_verdict,
          "evidence": f"缺项：{missing or '无'}"},
        {"layer": "L2_security", "verdict": l2["verdict"],
          "evidence": f"命中：{l2['hits'] or '无'}"},
        {"layer": "L3_overlap", "verdict": l3["verdict"],
          "evidence": f"疑似：{len(l3['suspects'])} 对"},
        {"layer": "L4_synth", "verdict": l4["verdict"],
          "evidence": f"合成题：{len(l4['questions'])} 道"},
        {"layer": "L5_live", "verdict": l5["verdict"],
          "evidence": l5["reason"]},
    ]
    blocking = [l for l in layers if l["verdict"] == "不过"]
    if blocking:
        admission = "不进（整改）"
    elif any(l["verdict"] == "疑似" for l in layers):
        admission = "待复核"
    elif any(l["verdict"] == "待补测" for l in layers):
        admission = "待补测"
    else:
        admission = "可进收件箱"
    return {"schema": ADMISSION_SCHEMA, "skill": skill.get("name", ""),
            "layers": layers, "admission": admission,
            "static_checks": l1, "security": l2, "overlap": l3,
            "synth": l4, "live": l5}


class AdmissionLedger:
    """检查结果 JSONL append-only 留痕（四件缺一拒绝入账）。"""

    def __init__(self, path: str | Path | None = None) -> None:
        self._records: list[dict[str, Any]] = []
        self._path = Path(path) if path else None

    def record(self, entry: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(entry, dict):
            raise AdmissionError("ENTRY_INVALID：条目非对象")
        missing = [k for k in PATTERN_REQUIRED
                   if k not in entry or not str(entry.get(k, "")).strip()]
        if missing:
            raise AdmissionError(
                f"ENTRY_INCOMPLETE：留痕条目缺 {missing}")
        rec = {"schema": ADMISSION_SCHEMA, **copy.deepcopy(entry)}
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
    """agent-native CLI：--skill <SKILL.md> --report <输出 md>。"""
    parser = argparse.ArgumentParser(description="技能准入检查 CLI")
    parser.add_argument("--skill", required=True, help="SKILL.md 路径")
    parser.add_argument("--report", required=True, help="报告输出路径")
    args = parser.parse_args(argv)
    text = Path(args.skill).read_text(encoding="utf-8")
    skill = {"name": scalar(frontmatter(text), "name")
             or Path(args.skill).parent.name, "text": text,
             "source_path": args.skill}
    report = run_admission(skill, [])
    out = Path(args.report)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(json.dumps({"admission": report["admission"],
                      "skill": report["skill"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
