# -*- coding: utf-8 -*-
"""技能评估最小实现（PRD-491/492/493/494/496 T2 共用口径，Python 版）。

只做两件 T2 验收要求的事：
  1. 质量门：按 T1 设计稿的阈值，对“有技能 vs 无技能”对照数据做判定。
  2. 重叠检测：技能两两比对，文本通道（Jaccard / TF-IDF 余弦）出疑似重叠候选对。

红线与边界（T1 设计稿）：
  - 只借鉴思路，不复用代码；零网络、零外部依赖（标准库 only）。
  - 评估结论只进整改清单（append-only JSONL），绝不直接删技能；
    重叠只判“疑似”，是否真重复由人工复核定，机器不自动合并、不自动删。
  - 语义通道（embedding 余弦 >= 0.85）需要向量模型选型（T1 待决策）：
    本实现不装模型、不伪造语义分，只跑文本通道，并在报告里如实注明
    “语义通道未跑”。评测题 / 实测是 T5 的事，本 T2 不做。
  - 不审产物、不审 agent 干活过程、不改技能包形态与上架流程。

质量门两种变体（按各仓 T1 设计稿）：
  - error-rate 变体（PRD-491/492）：错误率相对对照组下降 >= 20% 且任一
    类别恶化不超过 5 个百分点为过关；下降 0-20% 或某类恶化超 5pp 为待整改；
    错误率不降反升或对照不可复现为不过关；两轮结论不一致为待复核。
  - three-metric 变体（PRD-493/494/496）：三项全达标为过关——错误率相对
    基线下降 >= 20% 且绝对错误率 <= 5%、漏判率恶化 <= 2pp、触发率 >= 10%；
    触发率 < 10% 判疑似失效（进复核，不直接判死）；任一项不达标为未过关。
"""

import argparse
import json
import math
import re
import sys
from pathlib import Path

TEXT_THRESHOLD = 0.70          # 文本相似度疑似重叠阈值（T1 §2.2 初值）
SEMANTIC_THRESHOLD = 0.85      # 语义相似度阈值（T1 初值；需模型，未跑）
ERROR_DROP_PASS = 0.20         # 错误率相对下降过关线
CATEGORY_WORSEN_LIMIT = 0.05   # 单类恶化上限（5pp）
MISS_WORSEN_LIMIT = 0.02       # 漏判率恶化上限（2pp）
ABS_ERROR_LIMIT = 0.05         # 绝对错误率上限（5%）
TRIGGER_FLOOR = 0.10           # 触发率下限（10%）
REPORT_VERSION = "v1"
EVAL_DATE = "2026-11-17"

_CJK = re.compile(r"[\u4e00-\u9fff]+")
_WORD = re.compile(r"[A-Za-z0-9_]+")


def tokenize(text):
    """分词：ASCII 词 + 中文字符 bigram（中文按字切，避免整段中文成一个 token）。"""
    tokens = [w.lower() for w in _WORD.findall(text or "")]
    for run in _CJK.findall(text or ""):
        tokens.extend(run[i:i + 2] for i in range(len(run) - 1))
    return tokens


def jaccard(a, b):
    """Jaccard 相似度（token 集合）。"""
    sa, sb = set(tokenize(a)), set(tokenize(b))
    if not sa and not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def tfidf_cosine(texts):
    """TF-IDF 余弦相似度矩阵（纯标准库；与 Jaccard 互为印证的第二通道）。"""
    docs = [tokenize(t) for t in texts]
    df = {}
    for doc in docs:
        for tok in set(doc):
            df[tok] = df.get(tok, 0) + 1
    n = len(docs)
    vecs = []
    for doc in docs:
        tf = {}
        for tok in doc:
            tf[tok] = tf.get(tok, 0) + 1
        vec = {}
        for tok, c in tf.items():
            vec[tok] = (1.0 + math.log(c)) * math.log((n + 1.0) / (df[tok] + 0.5))
        vecs.append(vec)

    def cosine(u, v):
        num = sum(u[k] * v.get(k, 0.0) for k in u)
        du = math.sqrt(sum(x * x for x in u.values()))
        dv = math.sqrt(sum(x * x for x in v.values()))
        if du == 0.0 or dv == 0.0:
            return 0.0
        return num / (du * dv)

    return [[cosine(vecs[i], vecs[j]) for j in range(n)] for i in range(n)]


def detect_overlap(skills, text_threshold=TEXT_THRESHOLD):
    """两两重叠检测。只出“疑似重叠”候选对并附证据；不判真重复、不合并、不删。

    skills: [{"id":..., "name":..., "text":..., "source":...}, ...]
    返回 [{"skill_a","skill_b","jaccard","tfidf_cosine","shared_tokens",
           "verdict":"疑似重叠（待人工复核）","semantic":"未跑（待向量模型选型）"}]
    """
    pairs = []
    if len(skills) < 2:
        return pairs
    cos = tfidf_cosine([s["text"] for s in skills])
    for i in range(len(skills)):
        for j in range(i + 1, len(skills)):
            jac = jaccard(skills[i]["text"], skills[j]["text"])
            tf = cos[i][j]
            if jac >= text_threshold or tf >= text_threshold:
                shared = sorted(set(tokenize(skills[i]["text"])) &
                                set(tokenize(skills[j]["text"])))[:20]
                pairs.append({
                    "skill_a": skills[i]["id"],
                    "skill_b": skills[j]["id"],
                    "jaccard": round(jac, 4),
                    "tfidf_cosine": round(tf, 4),
                    "shared_tokens": shared,
                    "verdict": "疑似重叠（待人工复核）",
                    "semantic": "未跑（待向量模型选型，T1 待决策）",
                })
    return pairs


def quality_gate_error_rate(m):
    """error-rate 变体（PRD-491/492 T1 §二.1）。

    m: {"baseline_error_rate","skill_error_rate","category_worsening_pp":{},
        "rounds":[... verdicts per round ...], "control_reproducible": bool}
    返回 (verdict, reason)。
    """
    if not m.get("control_reproducible", True):
        return "不过关", "对照组不可复现（样本不足/任务漂移）"
    rounds = m.get("rounds") or []
    if len(rounds) >= 2 and len(set(rounds)) > 1:
        return "待复核", "两轮对照结论不一致"
    base = m["baseline_error_rate"]
    skill = m["skill_error_rate"]
    if base <= 0:
        return "待复核", "基线错误率为 0，相对下降无法计算"
    drop = (base - skill) / base
    worst = max((m.get("category_worsening_pp") or {}).values(), default=0.0)
    if drop < 0:
        return "不过关", "错误率不降反升（相对变化 %.1f%%）" % (drop * 100)
    if drop >= ERROR_DROP_PASS and worst <= CATEGORY_WORSEN_LIMIT:
        return "过关", "错误率相对下降 %.1f%%，单类最大恶化 %.1fpp" % (drop * 100, worst * 100)
    bits = []
    if drop < ERROR_DROP_PASS:
        bits.append("错误率相对下降 %.1f%%（< 20%%）" % (drop * 100))
    if worst > CATEGORY_WORSEN_LIMIT:
        bits.append("单类恶化 %.1fpp（> 5pp）" % (worst * 100))
    return "待整改", "；".join(bits)


def quality_gate_three_metric(m):
    """three-metric 变体（PRD-493/494/496 T1 §2.1）。

    m: {"baseline_error_rate","skill_error_rate","baseline_miss_rate",
        "skill_miss_rate","trigger_rate"}
    返回 (verdict, reason)。verdict in {过关, 未过关, 疑似失效}。
    """
    base = m["baseline_error_rate"]
    skill = m["skill_error_rate"]
    drop = (base - skill) / base if base > 0 else 0.0
    miss_delta = m["skill_miss_rate"] - m["baseline_miss_rate"]
    trigger = m["trigger_rate"]
    if trigger < TRIGGER_FLOOR:
        return "疑似失效", "触发率 %.1f%% < 10%%，进复核（不直接判死）" % (trigger * 100)
    if drop >= ERROR_DROP_PASS and skill <= ABS_ERROR_LIMIT and miss_delta <= MISS_WORSEN_LIMIT:
        return "过关", "错误率相对下降 %.1f%% 且绝对 %.1f%%，漏判恶化 %.1fpp，触发率 %.1f%%" % (
            drop * 100, skill * 100, miss_delta * 100, trigger * 100)
    reasons = []
    if drop < ERROR_DROP_PASS:
        reasons.append("错误率相对下降 %.1f%% < 20%%" % (drop * 100))
    if skill > ABS_ERROR_LIMIT:
        reasons.append("绝对错误率 %.1f%% > 5%%" % (skill * 100))
    if miss_delta > MISS_WORSEN_LIMIT:
        reasons.append("漏判率恶化 %.1fpp > 2pp" % (miss_delta * 100))
    return "未过关", "；".join(reasons)


def scan_skill_dir(skills_root):
    """扫描 <root>/*/SKILL.md，返回技能清单（id=目录名，text=全文）。"""
    root = Path(skills_root)
    skills = []
    if not root.is_dir():
        return skills
    for path in sorted(root.rglob("SKILL.md")):
        skills.append({
            "id": path.parent.name,
            "name": path.parent.name,
            "text": path.read_text(encoding="utf-8"),
            "source": str(path.relative_to(root.parent)) if root.parent in path.parents else str(path),
        })
    return skills


def load_inventory(path):
    """读技能清单 JSON（无 SKILL.md 的仓用；每条须注明来源文件）。"""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data["skills"]


def append_remediation(ledger_path, entries):
    """整改清单 append-only：只追加新条目，不改写历史。"""
    path = Path(ledger_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    return len(entries)


def run_evaluation(skills, measurements, variant, prd, repo, note=""):
    """跑一轮评估，返回报告 dict（不写盘；写盘由调用方/CLI 做）。"""
    gate = quality_gate_error_rate if variant == "error-rate" else quality_gate_three_metric
    gates = {}
    for s in skills:
        m = measurements.get(s["id"])
        if m is None:
            gates[s["id"]] = {"verdict": "未评定", "reason": "无对照数据，待真实对照复核"}
        else:
            verdict, reason = gate(m)
            gates[s["id"]] = {"verdict": verdict, "reason": reason,
                              "measurements": m, "data": "合成演示数据，待真实对照复核"}
    overlap = detect_overlap(skills)
    closest = None
    if len(skills) >= 2:
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
    return {
        "prd": prd, "repo": repo, "version": REPORT_VERSION, "date": EVAL_DATE,
        "skills": [{"id": s["id"], "name": s["name"], "source": s.get("source", "")}
                   for s in skills],
        "quality_gate_variant": variant,
        "quality_gate": gates,
        "overlap_candidates": overlap,
        "closest_pair_below_threshold": closest,
        "overlap_note": "文本通道（Jaccard/TF-IDF >= 0.70）已跑；语义通道（embedding 余弦 >= 0.85）"
                        "待向量模型选型，未跑。",
        "remediation_new_entries": remediation,
        "note": note or "首份评估报告（T2 最小实现）：重叠检测跑在真实技能文本上；"
                "质量门判定器已跑通，但对照数据为合成演示数据，结论待真实对照复核，"
                "实测在 T5 跑真实任务。",
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="技能评估最小实现（T2）：质量门 + 重叠检测")
    ap.add_argument("--prd", required=True)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--variant", choices=["error-rate", "three-metric"], required=True)
    ap.add_argument("--skills-dir", default="")
    ap.add_argument("--inventory", default="")
    ap.add_argument("--measurements", required=True, help="对照数据 JSON（演示数据须注明）")
    ap.add_argument("--report", required=True)
    ap.add_argument("--remediation", required=True)
    args = ap.parse_args(argv)

    if args.skills_dir:
        skills = scan_skill_dir(args.skills_dir)
    else:
        skills = load_inventory(args.inventory)
    measurements = json.loads(Path(args.measurements).read_text(encoding="utf-8"))
    report = run_evaluation(skills, measurements, args.variant, args.prd, args.repo)
    out = Path(args.report)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    n = append_remediation(args.remediation, report["remediation_new_entries"])
    print(json.dumps({"skills": len(skills), "overlap_candidates": len(report["overlap_candidates"]),
                      "remediation_appended": n, "report": str(out)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
