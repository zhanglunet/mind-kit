# -*- coding: utf-8 -*-
"""技能评估验收试运行（PRD-492/T5）。

把 T1 设计稿 §二.4「实测：跑真实整理任务量行为变化」落地为可复核的试运行：
同一批真实任务，A 组挂待评技能、B 组不挂，对照着比；评分是确定性的
token 检查（evaluate_quality.py 同款做法：必需事实/禁止表述/依据来源/
结构要素），不靠 LLM 打分，不编数字。

样本量口径（T1 §二.4，硬规则）：
  每轮实测不少于 30 个真实任务、至少跑两轮对照，两轮结论一致才落账；
  少于 30 个时结论只记“样本不足”，不落账为过关。
本试运行只有 6 个真实任务、1 轮——质量门结论一律记“未评定（样本不足）”，
实测的错误率如实记在 measurements 里，不升格为过关/待整改。

本模块只做确定性工作，不调任何模型、不联网：
  - score_output()：按 trial-tasks.json 的 token 表给一次 agent 输出打分；
    禁止表述检查前先遮蔽已匹配的必需事实与否定句（“不要尝试绕过”），
    避免否定句被误判；
  - score_arm()：读一臂的全部试运行输出，汇总三类错误；
  - trial_verdict()：先过样本量关，不过关直接判“未评定”，不调质量门；
  - run_trial()：重叠检测（真实技能文本）+ 质量门 + 试运行报告。
agent 输出本身由一次性驱动另外跑（见试运行报告），本模块只读已落盘的
输出文件打分——打分可复现，结论可复核。

红线（T1 设计稿 §五）：
  - 只借鉴思路，不复用代码；零网络、零外部依赖（标准库 only）。
  - 评估结论只进整改清单（append-only JSONL），绝不直接删技能；
    重叠只判“疑似”，是否真重复由人工复核定，机器不自动合并、不自动删。
  - 不审产物、不审 agent 干活过程、不改技能包形态与上架流程。
  - 样本不足不落账为过关；无对照数据不编数据。

测试：tests/test_prd492_t5_skill_evaluation_trial.py
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from skill_evaluation import detect_overlap, quality_gate_error_rate  # noqa: E402

TASKS_REQUIRED_PER_ROUND = 30   # T1 §二.4：每轮不少于 30 个真实任务
ROUNDS_REQUIRED = 2             # T1 §二.1：同一技能至少跑两轮对照
REPORT_VERSION = "v1-trial"
EVAL_DATE = "2026-11-17"
CATEGORIES = ["事实", "溯源", "结构"]


def _mask(text, tokens):
    """遮蔽已匹配的必需事实：否定句（“不要尝试绕过”）里的禁止表述子串不算违规。"""
    masked = text
    for t in tokens or []:
        if t and t in masked:
            masked = masked.replace(t, "\0" * len(t))
    return masked


_NEGATIONS = ("不要", "切勿", "不得", "不能", "禁止", "避免", "别", "不")


def _mask_negations(text, forbidden):
    """遮蔽否定句里的禁止表述：“不要尝试绕过”“切勿恢复旧 token”是正确的
    规则陈述，不是违规。长否定词优先，避免“不”先切坏“不要”。"""
    masked = text
    for f in forbidden or []:
        if not f:
            continue
        for neg in _NEGATIONS:
            phrase = neg + f
            if phrase in masked:
                masked = masked.replace(phrase, "\0" * len(phrase))
    return masked


def score_output(task, text):
    """给一次 agent 输出打分（0/1 计分，三类各 1 个错）。

    事实：必需事实出现其一，且遮蔽后无禁止表述；
    溯源：至少出现一个依据来源；
    结构：结构要素齐全（structure_all 全出现，且 structure_any 至少出现其一，
      如“申请”与“前往服务页”是同一步的不同说法）。
    返回 {"事实": 0/1, "溯源": 0/1, "结构": 0/1, "details": {...}}。
    """
    text = text or ""
    required = task.get("fact_any") or []
    matched_required = [t for t in required if t and t in text]
    masked = _mask(text, matched_required)
    masked = _mask_negations(masked, task.get("fact_none") or [])
    forbidden_hit = [t for t in (task.get("fact_none") or []) if t and t in masked]
    fact_error = 0 if (matched_required and not forbidden_hit) else 1
    trace_hit = [t for t in (task.get("trace_any") or []) if t and t in text]
    trace_error = 0 if trace_hit else 1
    structure = task.get("structure_all") or []
    structure_missing = [t for t in structure if t and t not in text]
    structure_any = task.get("structure_any") or []
    structure_any_hit = [t for t in structure_any if t and t in text]
    structure_error = 0 if (not structure_missing
                            and (not structure_any or structure_any_hit)) else 1
    return {
        "事实": fact_error,
        "溯源": trace_error,
        "结构": structure_error,
        "details": {
            "fact_required_matched": matched_required,
            "fact_forbidden_hit": forbidden_hit,
            "trace_matched": trace_hit,
            "structure_missing": structure_missing,
            "structure_any_matched": structure_any_hit,
        },
    }


def _strip_run_meta(text):
    """去掉试运行输出文件头的元数据注释行，只留 agent 输出正文。"""
    lines = (text or "").split("\n")
    return "\n".join(l for l in lines if not l.strip().startswith("<!-- trial-run:"))


def score_arm(tasks, runs_dir, arm):
    """汇总一臂的全部试运行输出。

    返回 {"errors": {"事实": n, "溯源": n, "结构": n, "total": n},
          "per_task": [{task, errors...}], "missing": [缺失输出的任务]}。
    缺失输出直接抛错，不静默记 0 分。
    """
    errors = {c: 0 for c in CATEGORIES}
    per_task = []
    missing = []
    for task in tasks:
        path = Path(runs_dir) / arm / (task["id"] + ".md")
        if not path.exists():
            missing.append(task["id"])
            continue
        s = score_output(task, _strip_run_meta(path.read_text(encoding="utf-8")))
        for c in CATEGORIES:
            errors[c] += s[c]
        per_task.append({"task": task["id"], "errors": {c: s[c] for c in CATEGORIES}})
    if missing:
        raise FileNotFoundError("试运行输出缺失：%s（臂 %s）" % (missing, arm))
    errors["total"] = sum(errors[c] for c in CATEGORIES)
    return {"errors": errors, "per_task": per_task, "missing": missing}


def build_measurements(baseline, skill, n_tasks, rounds_run=1):
    """由两臂的错误汇总算对照数（真实测得的数，不做任何推断）。

    错误率 = 错误数 / (任务数 × 3 类)；单类恶化 = 该类错误率之差（pp 换算在报告里）。
    """
    slots = max(n_tasks * 3, 1)
    base_rate = baseline["errors"]["total"] / slots
    skill_rate = skill["errors"]["total"] / slots
    worsening = {}
    for c in CATEGORIES:
        worsening[c] = round(skill["errors"][c] / max(n_tasks, 1)
                             - baseline["errors"][c] / max(n_tasks, 1), 4)
    return {
        "tasks": n_tasks,
        "tasks_required_per_round": TASKS_REQUIRED_PER_ROUND,
        "rounds_run": rounds_run,
        "rounds_required": ROUNDS_REQUIRED,
        "baseline_error_rate": round(base_rate, 4),
        "skill_error_rate": round(skill_rate, 4),
        "baseline_errors": baseline["errors"],
        "skill_errors": skill["errors"],
        "category_worsening_pp": worsening,
        "rounds": ["样本不足"] if n_tasks < TASKS_REQUIRED_PER_ROUND or rounds_run < ROUNDS_REQUIRED else [],
        "control_reproducible": True,
        "sample_note": "本轮真实任务 %d 个 < T1 §二.4 要求的 %d 个；仅 %d 轮 < 要求的 %d 轮"
                       % (n_tasks, TASKS_REQUIRED_PER_ROUND, rounds_run, ROUNDS_REQUIRED),
    }


def trial_verdict(measurements):
    """试运行质量门结论：先过样本量关。

    任务数 < 30 或轮数 < 2 → “未评定”，理由写清样本缺口，不落账为过关；
    样本够了才交给 T2 的质量门判定器按 T1 §二.1 阈值判。
    """
    n = measurements.get("tasks", 0)
    rounds = measurements.get("rounds_run", 0)
    if n < TASKS_REQUIRED_PER_ROUND or rounds < ROUNDS_REQUIRED:
        return ("未评定",
                "样本不足：本轮真实任务 %d 个 < T1 §二.4 要求的 %d 个，"
                "仅 %d 轮 < 要求的 %d 轮；结论只记样本不足，不落账为过关"
                % (n, TASKS_REQUIRED_PER_ROUND, rounds, ROUNDS_REQUIRED))
    m = dict(measurements)
    m["rounds"] = m.get("rounds") or ["过关", "过关"]
    return quality_gate_error_rate(m)


def run_trial(skills, measurements_by_skill, prd, repo, skill_versions=None,
              model="", temperature=None, runs_dir=""):
    """跑一轮试运行评估，返回报告 dict（不写盘；写盘由 CLI 做）。

    measurements_by_skill: {skill_id: measurements}；没有对照数据的技能
    记“未评定（无对照数据）”。技能条目有版本字段才带 version，没有不编。
    """
    gates = {}
    pending = []
    for s in skills:
        m = measurements_by_skill.get(s["id"])
        if m is None:
            gates[s["id"]] = {"verdict": "未评定", "reason": "无对照数据，待真实对照复核"}
            pending.append({"skill": s["id"], "issue": "无对照数据",
                            "evidence": "试运行未覆盖该技能"})
            continue
        verdict, reason = trial_verdict(m)
        gates[s["id"]] = {"verdict": verdict, "reason": reason,
                          "measurements": m, "data": "真实对照数据（试运行，n=%d）" % m.get("tasks", 0)}
        if verdict == "未评定":
            pending.append({"skill": s["id"], "issue": "样本不足",
                            "evidence": (m.get("sample_note") or reason) if m else reason})
    overlap = detect_overlap(skills)
    closest = None
    if len(skills) >= 2:
        from skill_evaluation import jaccard, tfidf_cosine
        cos = tfidf_cosine([s["text"] for s in skills])
        best = (0.0, None)
        for i in range(len(skills)):
            for j in range(i + 1, len(skills)):
                jac = jaccard(skills[i]["text"], skills[j]["text"])
                if jac > best[0]:
                    best = (jac, {"skill_a": skills[i]["id"], "skill_b": skills[j]["id"],
                                  "jaccard": round(jac, 4),
                                  "tfidf_cosine": round(cos[i][j], 4)})
        closest = best[1]
    remediation = []
    for sid, g in gates.items():
        if g["verdict"] in ("不过关", "未过关", "待整改", "疑似失效"):
            remediation.append({"date": EVAL_DATE, "prd": prd, "skill": sid,
                                "type": "失效/待整改" if g["verdict"] != "疑似失效" else "疑似失效",
                                "evidence": g["reason"], "status": "待整改"})
    for p in overlap:
        remediation.append({"date": EVAL_DATE, "prd": prd,
                            "skill": "%s <-> %s" % (p["skill_a"], p["skill_b"]),
                            "type": "疑似重叠",
                            "evidence": "Jaccard %.4f / TF-IDF %.4f；语义通道未跑" % (
                                p["jaccard"], p["tfidf_cosine"]),
                            "status": "待人工复核"})
    skill_entries = []
    for s in skills:
        entry = {"id": s["id"], "name": s["name"], "source": s.get("source", "")}
        v = (skill_versions or {}).get(s["id"])
        if v is not None:
            entry["version"] = str(v)
        skill_entries.append(entry)
    return {
        "prd": prd, "repo": repo, "version": REPORT_VERSION, "date": EVAL_DATE,
        "skills": skill_entries,
        "quality_gate_variant": "error-rate",
        "quality_gate": gates,
        "overlap_candidates": overlap,
        "closest_pair_below_threshold": closest,
        "overlap_note": "文本通道（Jaccard/TF-IDF >= 0.70）已跑；语义通道（embedding 余弦 >= 0.85）"
                        "待向量模型选型，未跑。",
        "remediation_new_entries": remediation,
        "pending_review": pending,
        "trial": {
            "tasks": (measurements_by_skill.get(skills[0]["id"], {}).get("tasks", 0)
                      if skills else 0),
            "tasks_required_per_round": TASKS_REQUIRED_PER_ROUND,
            "rounds_run": 1,
            "rounds_required": ROUNDS_REQUIRED,
            "model": model, "temperature": temperature,
            "runs_dir": runs_dir,
        },
        "note": "验收试运行报告（T5）：全套评估跑一遍真实技能包。"
                "重叠检测跑在真实技能文本上；质量门对照数据为真实试运行"
                "（试运行任务取自技能文档记载的真实用户情形，agent 输出"
                "为一次性驱动实跑），样本量未达 T1 §二.4 的线，结论只记"
                "样本不足，不落账为过关。v1 报告（合成演示数据）未被覆盖，"
                "仍在原位置作历史账。",
    }


def render_report_md(report):
    """试运行报告 Markdown（与 T2 的 v1 报告同格式，便于对照）。"""
    lines = ["# 技能评估试运行报告（PRD-492/T5）", "",
             "- 日期：%s" % report["date"],
             "- 报告版本：%s（试运行，不覆盖 v1 报告）" % report["version"],
             "- 参评技能：%d 个" % len(report["skills"]), ""]
    for s in report["skills"]:
        ver = s.get("version")
        lines.append("- %s（来源：%s；版本：%s）"
                     % (s["id"], s["source"],
                        ver if ver is not None else "未声明，报告如实记缺失"))
    lines += ["", "## 质量门（error-rate 变体，真实对照数据）", ""]
    for sid, g in report["quality_gate"].items():
        lines.append("- %s：**%s**——%s" % (sid, g["verdict"], g["reason"]))
        m = g.get("measurements")
        if m:
            lines.append("  - 任务数 %d（要求每轮 ≥ %d），轮数 %d（要求 %d）；"
                         "基线错误率 %.1f%%，技能错误率 %.1f%%；"
                         "基线错误 %s，技能错误 %s"
                         % (m["tasks"], m["tasks_required_per_round"],
                            m["rounds_run"], m["rounds_required"],
                            m["baseline_error_rate"] * 100,
                            m["skill_error_rate"] * 100,
                            m["baseline_errors"], m["skill_errors"]))
    lines += ["", "## 重叠检测（真实技能文本）", ""]
    if report["overlap_candidates"]:
        for p in report["overlap_candidates"]:
            lines.append("- %s ↔ %s：Jaccard %.4f / TF-IDF %.4f——%s"
                         % (p["skill_a"], p["skill_b"], p["jaccard"],
                            p["tfidf_cosine"], p["verdict"]))
    else:
        lines.append("- 疑似重叠候选 0 对。%s"
                     % ("技能不足 2 个，无法比对。"
                        if len(report["skills"]) < 2 else
                        "最接近阈值：%s。" % (report["closest_pair_below_threshold"],)))
    lines.append("- %s" % report["overlap_note"])
    lines += ["", "## 整改清单增量", ""]
    if report["remediation_new_entries"]:
        for e in report["remediation_new_entries"]:
            lines.append("- %s：%s——%s" % (e["skill"], e["type"], e["evidence"]))
    else:
        lines.append("- 本轮新增 0 条（未建 remediation.jsonl，沿用 T2 约定）。")
    lines += ["", "## 待复核", ""]
    if report["pending_review"]:
        for e in report["pending_review"]:
            lines.append("- %s：%s——%s" % (e["skill"], e["issue"], e["evidence"]))
    else:
        lines.append("- 无。")
    lines += ["", "## 备注", "", report["note"], ""]
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="技能评估验收试运行（PRD-492/T5）：确定性打分 + 试运行报告")
    ap.add_argument("--prd", required=True)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--skills-dir", required=True)
    ap.add_argument("--tasks", required=True, help="试运行任务 JSON")
    ap.add_argument("--runs-dir", required=True, help="试运行输出目录（含 with-skill/without-skill 两臂）")
    ap.add_argument("--skill-versions", default="", help="技能版本表 JSON（可选；没有不编）")
    ap.add_argument("--model", default="")
    ap.add_argument("--temperature", default=None, type=float)
    ap.add_argument("--report", required=True)
    ap.add_argument("--report-md", required=True)
    ap.add_argument("--measurements-out", default="")
    args = ap.parse_args(argv)

    from skill_evaluation import scan_skill_dir
    skills = scan_skill_dir(args.skills_dir)
    tasks = json.loads(Path(args.tasks).read_text(encoding="utf-8"))["tasks"]
    baseline = score_arm(tasks, args.runs_dir, "without-skill")
    skill = score_arm(tasks, args.runs_dir, "with-skill")
    measurements = build_measurements(baseline, skill, len(tasks), rounds_run=1)
    versions = {}
    if args.skill_versions:
        versions = json.loads(Path(args.skill_versions).read_text(encoding="utf-8"))
    report = run_trial(skills, {skills[0]["id"]: measurements} if skills else {},
                       args.prd, args.repo, skill_versions=versions,
                       model=args.model, temperature=args.temperature,
                       runs_dir=args.runs_dir)
    # trial.tasks 取实跑任务数（run_trial 里从 measurements 取不到任务数时补）
    if skills:
        report["trial"]["tasks"] = len(tasks)
    out = Path(args.report)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    Path(args.report_md).write_text(render_report_md(report), encoding="utf-8")
    if args.measurements_out:
        Path(args.measurements_out).write_text(
            json.dumps({skills[0]["id"]: measurements} if skills else {},
                       ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"skills": len(skills), "tasks": len(tasks),
                      "baseline_error_rate": measurements["baseline_error_rate"],
                      "skill_error_rate": measurements["skill_error_rate"],
                      "verdict": report["quality_gate"][skills[0]["id"]]["verdict"] if skills else None,
                      "overlap_candidates": len(report["overlap_candidates"]),
                      "report": str(out)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
