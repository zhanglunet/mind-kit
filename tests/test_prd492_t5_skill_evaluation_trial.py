# -*- coding: utf-8 -*-
"""技能评估 T5 测试（PRD-492/T5 验收试运行）。

运行：python3 -m pytest tests/test_prd492_t5_skill_evaluation_trial.py -q
零网络、零外部依赖；试运行输出打分是确定性 token 检查，不调模型。
"""
import ast
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from skill_trial import (  # noqa: E402
    build_measurements,
    render_report_md,
    run_trial,
    score_arm,
    score_output,
    trial_verdict,
)

TASK = {
    "id": "t1",
    "task": "公开版想同步飞书怎么办？",
    "fact_any": ["公开包不含", "不含飞书同步"],
    "fact_none": ["可以拼凑", "改安装器"],
    "trace_any": ["服务页", "完整发行包"],
    "structure_all": ["公开包", "申请"],
}


def test_score_output_all_pass():
    text = ("公开包不含飞书同步连接器，这是设计不是故障。"
            "需要同步请到服务页申请完整发行包。")
    s = score_output(TASK, text)
    assert s == {"事实": 0, "溯源": 0, "结构": 0, "details": s["details"]}


def test_score_output_fact_missing_and_forbidden():
    s = score_output(TASK, "可以拼凑一个连接器，从别处找就行。")
    assert s["事实"] == 1  # 必需事实没出现
    s = score_output(TASK, "公开包不含飞书同步，但可以拼凑一个连接器。")
    assert s["事实"] == 1  # 出现禁止表述
    assert "可以拼凑" in s["details"]["fact_forbidden_hit"]


def test_score_output_negation_not_a_false_positive():
    # “不要尝试绕过”是否定句，不应被当成违规；遮蔽后禁止表述不出现。
    task = dict(TASK, fact_any=["公开包不含"], fact_none=["尝试绕过"])
    s = score_output(task, "公开包不含飞书同步，不要尝试绕过安装器。")
    assert s["事实"] == 0


def test_score_output_structure_any_accepts_alternative_wording():
    # “前往服务页”与“申请”是同一步的不同说法，任一出现即算结构要素齐全。
    task = dict(TASK, structure_all=["公开包"], structure_any=["申请", "前往服务页"])
    s = score_output(task, "公开包不含飞书同步，请前往服务页。")
    assert s["结构"] == 0
    s = score_output(task, "公开包不含飞书同步，请到服务页申请。")
    assert s["结构"] == 0
    s = score_output(task, "公开包不含飞书同步。")
    assert s["结构"] == 1  # 下一步两种说法都没出现


def test_score_output_trace_and_structure():
    s = score_output(TASK, "公开包不含飞书同步。")
    assert s["溯源"] == 1  # 无依据来源
    assert s["结构"] == 1  # 缺“申请”


def test_sample_rule_small_sample_is_not_passed():
    # 6 个任务、1 轮：实测错误率再漂亮也不落账为过关。
    base = {"errors": {"事实": 0, "溯源": 0, "结构": 0, "total": 0}, "per_task": [], "missing": []}
    skill = {"errors": {"事实": 0, "溯源": 0, "结构": 0, "total": 0}, "per_task": [], "missing": []}
    m = build_measurements(base, skill, 6, rounds_run=1)
    assert m["baseline_error_rate"] == 0.0 and m["skill_error_rate"] == 0.0
    verdict, reason = trial_verdict(m)
    assert verdict == "未评定"
    assert "样本不足" in reason


def test_sample_rule_enough_sample_delegates_to_gate():
    base = {"errors": {"事实": 9, "溯源": 0, "结构": 0, "total": 9}, "per_task": [], "missing": []}
    skill = {"errors": {"事实": 5, "溯源": 1, "结构": 1, "total": 7}, "per_task": [], "missing": []}
    m = build_measurements(base, skill, 30, rounds_run=2)
    m["rounds"] = ["过关", "过关"]
    verdict, _ = trial_verdict(m)
    assert verdict == "过关"  # 下降 22.2%，单类恶化 1/30=3.3pp < 5pp
    m2 = build_measurements(base, skill, 30, rounds_run=1)
    assert trial_verdict(m2)[0] == "未评定"  # 轮数不够也判样本不足


def test_score_arm_missing_output_raises():
    with tempfile.TemporaryDirectory() as d:
        try:
            score_arm([TASK], d, "with-skill")
        except FileNotFoundError as e:
            assert "t1" in str(e)
        else:
            raise AssertionError("缺失输出应抛错，不静默记 0 分")


def test_run_trial_single_skill_no_overlap_no_version():
    skills = [{"id": "only", "name": "only", "text": "安装技能 安装 安装",
               "source": "skills/only/SKILL.md"}]
    m = {"tasks": 6, "tasks_required_per_round": 30, "rounds_run": 1,
         "rounds_required": 2, "baseline_error_rate": 0.5,
         "skill_error_rate": 0.33, "baseline_errors": {}, "skill_errors": {},
         "category_worsening_pp": {}, "rounds": ["样本不足"],
         "control_reproducible": True, "sample_note": "x"}
    rep = run_trial(skills, {"only": m}, "PRD-492", "mind-kit")
    assert rep["version"] == "v1-trial"
    assert rep["quality_gate"]["only"]["verdict"] == "未评定"
    assert rep["overlap_candidates"] == []
    assert rep["closest_pair_below_threshold"] is None
    assert "version" not in rep["skills"][0]  # 无版本字段不编
    assert rep["remediation_new_entries"] == []  # 未评定不进整改清单
    assert rep["pending_review"][0]["issue"] == "样本不足"
    md = render_report_md(rep)
    assert "未评定" in md and "样本不足" in md and "无法比对" in md


def test_run_trial_no_measurements_is_unrated():
    skills = [{"id": "only", "name": "only", "text": "安装", "source": "s"}]
    rep = run_trial(skills, {}, "PRD-492", "mind-kit")
    assert rep["quality_gate"]["only"]["verdict"] == "未评定"
    assert "无对照数据" in rep["quality_gate"]["only"]["reason"]


def test_module_zero_network_ast():
    for name in ("skill_trial.py", "skill_evaluation.py", "evaluation_gate.py"):
        src = (Path(__file__).resolve().parents[1] / "scripts" / name).read_text(encoding="utf-8")
        tree = ast.parse(src)
        banned = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                banned.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                banned.add(node.module.split(".")[0])
        assert not (banned & {"urllib", "requests", "http", "socket", "subprocess"}), (name, banned)
