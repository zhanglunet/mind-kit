# -*- coding: utf-8 -*-
"""技能评估监督回路闸门（PRD-492/T3）。

把 T1 设计稿（docs/plans/2026-11-17-prd-492-mindkit-skill-evaluation-design.md）
§三「评估结果落账」里的闸门一段落地为显式、可测试的裁决：
  评估未过关的技能不得进入下游——其产物进不了评审流水线
  （PRD-433）的“可直接过”通道，只能走人工审校。

本模块只读 T2（scripts/skill_evaluation.py）的评估账本做裁决，
不重新判定质量门、不改写评估报告、不删技能：
  - gate_check()：单技能裁决的纯函数，只看账本（评估报告 quality_gate
    + 整改清单 remediation.jsonl），返回放行 / 拦截 + 封闭词表里的拦因；
  - route_product()：产物放行裁决的纯函数，只回答“这件产物走
    可直接过通道还是人工审校”，不真的改评审流水线代码；
  - finalize()：整批硬闸门——有一个技能未过关，整批拒绝；
  - decide_and_audit()：裁决 + 落一条审计记录（append-only JSONL，
    时间可注入以便逐字节复现），审计记清谁、什么时候、按哪份报告、
    判了什么。

关口断言（显式、可测试）：
  1. 放行当且仅当该技能有“过关”结论且无未处理整改项；
     无记录 / 未过关 / 待整改 / 待复核 / 未评定 / 有未处理整改项一律拦下，
     并给出封闭词表里的拦因；
  2. 裁决只看账本，不看时间——结论再旧，待复核照样拦下；
     模块内无任何超时自动通过的代码路径（没有默认通过）；
  3. 版本比对只在账本记录了技能版本时生效：T2 的 v1 报告未记录
     技能版本（见 T2 开发记录），无版本可比时闸门按结论裁决，并在
     审计记录里记下被问到的版本（version_asked）；账本带版本且与
     被问版本不一致即拦下（version_mismatch），旧版的过关结论
     不顺延到新版；
  4. 整改清单 append-only：闸门只读整改清单，绝不改写历史条目；
     闸门自己的落账只写审计记录（append-only JSONL），不碰评估报告；
  5. 闸门只拦，不改评估结论；评估只进整改清单，技能下线另走审批，
     闸门绝不直接删技能。

零网络、零外部依赖（标准库 only）；示例全合成占位。
测试：tests/test_prd492_t3_evaluation_gate.py
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

GATE_SCHEMA = "skill-evaluation-gate/v1"
GATE_ERROR_CODE = "GATE_NOT_ALL_PASSED"
# 拦下原因（封闭词表）：无记录 / 评估未过关 / 待整改 / 评估待复核 /
# 有未处理整改项 / 版本不匹配 / 记录无效。
BLOCKED_REASONS = [
    "no_record", "failed", "needs_remediation", "pending_review",
    "open_remediation", "version_mismatch", "invalid_record",
]
# 整改条目视为“已处理”的状态；其余一律视为未处理，照样拦。
HANDLED_REMEDIATION_STATUSES = ["已处理", "已关闭", "已复核", "已下线"]
# T2 质量门结论到闸门拦因的映射（过关不在其中——过关再查整改清单）。
VERDICT_REASONS = {
    "不过关": "failed",
    "未过关": "failed",
    "待整改": "needs_remediation",
    "待复核": "pending_review",
    "未评定": "pending_review",
    "疑似失效": "pending_review",
}
# 退出码：0 放行，1 拦截（走人工审校），2 用法/报告无效（fail-closed）。
EXIT_ALLOW = 0
EXIT_BLOCK = 1
EXIT_ERROR = 2


def _utcnow():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _blocked(skill_id, version, expected_version, version_asked,
             reason, verdict, as_of):
    return {
        "schema": GATE_SCHEMA, "gate": "blocked", "skill_id": skill_id,
        "version": version, "expected_version": expected_version,
        "version_asked": version_asked, "reason": reason,
        "verdict": verdict, "as_of": as_of,
    }


def _passed(skill_id, version, expected_version, version_asked,
            verdict, as_of):
    return {
        "schema": GATE_SCHEMA, "gate": "passed", "skill_id": skill_id,
        "version": version, "expected_version": expected_version,
        "version_asked": version_asked, "reason": "passed",
        "verdict": verdict, "as_of": as_of,
    }


def affected_skills(entry):
    """整改条目影响的技能：单技能条目取 skill 本身；重叠条目
    （skill 为 "a <-> b"）同时影响对子里的两个技能。"""
    raw = str((entry or {}).get("skill") or "").strip()
    if not raw:
        return []
    return [s.strip() for s in raw.split("<->") if s.strip()]


def is_handled_remediation(entry):
    """整改条目是否已处理（状态在已处理词表里才算处理完）。"""
    return str((entry or {}).get("status") or "") in HANDLED_REMEDIATION_STATUSES


def parse_remediation_jsonl(text):
    """解析整改清单 JSONL 文本：空行跳过；坏行直接抛错，不静默丢弃。"""
    entries = []
    for line in str(text or "").split("\n"):
        if not line.strip():
            continue
        entries.append(json.loads(line))
    return entries


def load_ledger(report, remediation_entries, skill_versions=None):
    """把 T2 评估账本（报告对象 + 整改清单条目数组）归一化为闸门可读的账本。

    skill_versions：可选的显式技能版本表 {skill_id: version}；账本本身
    （report.skills[].version）带版本时优先用账本的，显式表只补没有的。
    T2 的 v1 报告未记录技能版本——此时 versions 为空，版本比对不生效
    （见模块头注释第 3 条），不因此把全部技能拦下。
    """
    if not isinstance(report, dict):
        raise ValueError("invalid evaluation report: report must be an object")
    gate = report.get("quality_gate")
    if not isinstance(gate, dict):
        raise ValueError("invalid evaluation report: missing quality_gate")
    verdicts = {}
    for skill_id, entry in gate.items():
        verdicts[skill_id] = {
            "verdict": (entry or {}).get("verdict"),
            "reason": (entry or {}).get("reason") or "",
        }
    versions = {}
    for s in (report.get("skills") or []):
        if isinstance(s, dict) and isinstance(s.get("id"), str) \
                and s.get("version") is not None:
            versions[s["id"]] = str(s["version"])
    for skill_id, v in (skill_versions or {}).items():
        if skill_id not in versions and v is not None:
            versions[skill_id] = str(v)
    return {
        "verdicts": verdicts,
        "versions": versions,
        "remediation": list(remediation_entries or []),
        "report_version": report.get("version"),
        "report_date": report.get("date"),
        "prd": report.get("prd"),
    }


def open_remediation_for(ledger, skill_id):
    """该技能名下未处理的整改条目（重叠条目同时算到对子双方）。"""
    open_items = []
    for e in ledger["remediation"]:
        if skill_id in affected_skills(e) and not is_handled_remediation(e):
            open_items.append(e)
    return open_items


def gate_check(skill_id, ledger, as_of=None, expected_version=None):
    """单技能裁决（纯函数）：只看账本，不写任何东西。

    as_of：裁决时间（ISO；可注入以便复现，默认当前 UTC 时间）。
    expected_version：下游拿着的技能版本（可选）；账本有版本且不一致
      即拦下；账本无版本时按结论裁决，并记下被问到的版本。
    返回裁决 dict（含 gate passed/blocked、reason、version、version_asked）。
    """
    when = as_of or _utcnow()
    expected = str(expected_version) if expected_version is not None else None
    entry = ledger["verdicts"].get(skill_id)
    if entry is None:
        return _blocked(skill_id, None, expected, False,
                        "no_record", None, when)
    verdict = entry["verdict"]
    version = ledger["versions"].get(skill_id)
    version_asked = expected is not None and version is None
    if verdict in VERDICT_REASONS:
        return _blocked(skill_id, version, expected, version_asked,
                        VERDICT_REASONS[verdict], verdict, when)
    if verdict != "过关":
        return _blocked(skill_id, version, expected, version_asked,
                        "invalid_record", verdict, when)
    if expected is not None and version is not None and expected != version:
        return _blocked(skill_id, version, expected, False,
                        "version_mismatch", verdict, when)
    if open_remediation_for(ledger, skill_id):
        return _blocked(skill_id, version, expected, version_asked,
                        "open_remediation", verdict, when)
    return _passed(skill_id, version, expected, version_asked, verdict, when)


def route_product(skill_id, ledger, as_of=None, expected_version=None):
    """产物放行裁决（纯函数）：只回答“这件产物走可直接过通道还是
    人工审校”，不真的改评审流水线代码。"""
    d = gate_check(skill_id, ledger, as_of=as_of,
                   expected_version=expected_version)
    return {
        "skill_id": skill_id,
        "channel": "可直接过" if d["gate"] == "passed" else "人工审校",
        "gate": d["gate"],
        "reason": d["reason"],
        "verdict": d["verdict"],
    }


def finalize(skill_ids, ledger, as_of=None, expected_versions=None):
    """整批硬闸门：逐个裁决，有一个技能未过关，整批拒绝。

    返回 {"gate": "passed"/"blocked", "decisions": [...],
          "error_code": "GATE_NOT_ALL_PASSED" | None}。
    """
    expected_versions = expected_versions or {}
    decisions = [gate_check(s, ledger, as_of=as_of,
                            expected_version=expected_versions.get(s))
                 for s in skill_ids]
    blocked = [d for d in decisions if d["gate"] == "blocked"]
    return {
        "gate": "blocked" if blocked else "passed",
        "decisions": decisions,
        "error_code": GATE_ERROR_CODE if blocked else None,
        "blocked_skills": [d["skill_id"] for d in blocked],
    }


def append_audit(audit_path, record):
    """审计记录 append-only：只追加一行，不改写历史。"""
    path = Path(audit_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return 1


def decide_and_audit(skill_id, ledger, audit_path, actor, report_ref,
                     as_of=None, expected_version=None):
    """裁决 + 落账：gate_check() 的裁决连同审计字段追加进审计记录。

    审计记清：谁（actor）、什么时候（timestamp）、按哪份报告
    （report_ref：{path, date, version}）、判了什么（gate/reason/verdict）。
    返回裁决 dict。
    """
    when = as_of or _utcnow()
    decision = gate_check(skill_id, ledger, as_of=when,
                          expected_version=expected_version)
    record = {
        "schema": GATE_SCHEMA,
        "timestamp": when,
        "actor": actor,
        "report": report_ref,
        "skill_id": skill_id,
        "version": decision["version"],
        "expected_version": decision["expected_version"],
        "version_asked": decision["version_asked"],
        "verdict": decision["verdict"],
        "gate": decision["gate"],
        "reason": decision["reason"],
        "channel": "可直接过" if decision["gate"] == "passed" else "人工审校",
    }
    append_audit(audit_path, record)
    return decision


def load_report_file(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_remediation_file(path):
    """读整改清单文件；文件不存在视为 0 条（T2 未建清单时即如此）。"""
    p = Path(path)
    if not p.exists():
        return []
    return parse_remediation_jsonl(p.read_text(encoding="utf-8"))


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="技能评估监督回路闸门（PRD-492/T3）：按 T2 评估报告裁决"
                    "技能产物走可直接过通道还是人工审校")
    ap.add_argument("--report", required=True, help="T2 评估报告 JSON 路径")
    ap.add_argument("--skill", required=True, help="待裁决的技能 id")
    ap.add_argument("--remediation", required=True,
                    help="整改清单 JSONL 路径；不存在视为 0 条")
    ap.add_argument("--audit", default="",
                    help="审计记录 JSONL 路径；默认与报告同目录的 gate_audit.jsonl")
    ap.add_argument("--actor", default=os.environ.get("USER", "evaluation-gate"),
                    help="裁决执行人（默认取 $USER）")
    ap.add_argument("--expected-version", default=None,
                    help="下游拿着的技能版本；账本有版本且不一致即拦下")
    ap.add_argument("--as-of", default=None,
                    help="裁决时间 ISO（默认当前 UTC；测试复现用）")
    args = ap.parse_args(argv)

    try:
        report = load_report_file(args.report)
        ledger = load_ledger(report, load_remediation_file(args.remediation))
    except (OSError, ValueError, json.JSONDecodeError) as e:
        print("gate error: %s" % e, file=sys.stderr)
        return EXIT_ERROR
    audit_path = args.audit or str(
        Path(args.report).parent / "gate_audit.jsonl")
    report_ref = {"path": args.report, "date": report.get("date"),
                  "version": report.get("version")}
    decision = decide_and_audit(
        args.skill, ledger, audit_path, args.actor, report_ref,
        as_of=args.as_of, expected_version=args.expected_version)
    print(json.dumps(decision, ensure_ascii=False))
    return EXIT_ALLOW if decision["gate"] == "passed" else EXIT_BLOCK


if __name__ == "__main__":
    sys.exit(main())
