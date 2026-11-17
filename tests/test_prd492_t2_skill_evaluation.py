# -*- coding: utf-8 -*-
"""技能评估 T2 测试（PRD-492/493/496 共用口径；按仓只跑对应变体）。

运行：python3 -m pytest tests/test_prd<N>_t2_skill_evaluation.py -q
零网络、零外部依赖；对照数据全合成占位。
"""
import ast
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from skill_evaluation import (  # noqa: E402
    append_remediation,
    detect_overlap,
    jaccard,
    quality_gate_error_rate,
    quality_gate_three_metric,
    run_evaluation,
    tfidf_cosine,
    tokenize,
)

VARIANT = "three-metric"  # 占位：各仓文件把此行改成对应变体再跑全量


def test_tokenize_cjk_bigrams():
    toks = tokenize("海报技能评估")
    assert "海报" in toks and "报技" in toks
    assert "poster" in tokenize("Poster Skill")


def test_jaccard_identical_and_disjoint():
    assert jaccard("hello world", "hello world") == 1.0
    assert jaccard("alpha beta", "gamma delta") == 0.0


def test_tfidf_identical_high_disjoint_zero():
    cos = tfidf_cosine(["hello world", "hello world", "gamma delta"])
    assert cos[0][1] > 0.99
    assert cos[0][2] == 0.0


def test_overlap_identical_pair_is_candidate():
    skills = [
        {"id": "a", "name": "a", "text": "纠正发音错误 影子跟读 反馈", "source": "x"},
        {"id": "b", "name": "b", "text": "纠正发音错误 影子跟读 反馈", "source": "y"},
    ]
    pairs = detect_overlap(skills)
    assert len(pairs) == 1
    assert pairs[0]["skill_a"] == "a" and pairs[0]["skill_b"] == "b"
    assert pairs[0]["verdict"] == "疑似重叠（待人工复核）"
    assert pairs[0]["semantic"].startswith("未跑")


def test_overlap_disjoint_pair_is_not_candidate():
    skills = [
        {"id": "a", "name": "a", "text": "发音 纠正 最小对立对 跟读", "source": "x"},
        {"id": "b", "name": "b", "text": "待办 提取 截止日期 提醒 推送", "source": "y"},
    ]
    assert detect_overlap(skills) == []


def test_overlap_single_skill_no_pairs():
    skills = [{"id": "only", "name": "only", "text": "唯一技能", "source": "x"}]
    assert detect_overlap(skills) == []


def test_gate_error_rate_pass_boundary_and_fail():
    base = {"baseline_error_rate": 0.30, "skill_error_rate": 0.24,
            "category_worsening_pp": {}, "rounds": ["过关", "过关"],
            "control_reproducible": True}
    assert quality_gate_error_rate(base)[0] == "过关"  # 正好下降 20%
    m = dict(base, skill_error_rate=0.26)
    assert quality_gate_error_rate(m)[0] == "待整改"  # 下降 13.3%
    m = dict(base, skill_error_rate=0.31)
    assert quality_gate_error_rate(m)[0] == "不过关"  # 不降反升
    m = dict(base, category_worsening_pp={"文案": 0.06})
    assert quality_gate_error_rate(m)[0] == "待整改"  # 单类恶化超 5pp
    m = dict(base, rounds=["过关", "待整改"])
    assert quality_gate_error_rate(m)[0] == "待复核"  # 两轮不一致
    m = dict(base, control_reproducible=False)
    assert quality_gate_error_rate(m)[0] == "不过关"  # 对照不可复现


def test_gate_three_metric_pass_fail_suspect():
    base = {"baseline_error_rate": 0.10, "skill_error_rate": 0.04,
            "baseline_miss_rate": 0.20, "skill_miss_rate": 0.19,
            "trigger_rate": 0.35}
    assert quality_gate_three_metric(base)[0] == "过关"
    m = dict(base, skill_error_rate=0.06)
    assert quality_gate_three_metric(m)[0] == "未过关"  # 绝对错误率 6% > 5%
    m = dict(base, skill_miss_rate=0.23)
    assert quality_gate_three_metric(m)[0] == "未过关"  # 漏判恶化 3pp > 2pp
    m = dict(base, trigger_rate=0.08)
    assert quality_gate_three_metric(m)[0] == "疑似失效"  # 触发率 < 10%


def test_remediation_ledger_append_only():
    with tempfile.TemporaryDirectory() as d:
        ledger = Path(d) / "remediation.jsonl"
        append_remediation(ledger, [{"skill": "a", "status": "待整改"}])
        first = ledger.read_text(encoding="utf-8")
        append_remediation(ledger, [{"skill": "b", "status": "待人工复核"}])
        lines = ledger.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["skill"] == "a"  # 历史条目未被改写
        assert first.splitlines()[0] == lines[0]


def test_run_evaluation_report_shape():
    skills = [{"id": "a", "name": "a", "text": "甲乙丙", "source": "s"},
              {"id": "b", "name": "b", "text": "甲乙丁", "source": "s"}]
    rep = run_evaluation(skills, {}, "three-metric", "PRD-000", "repo-x")
    assert rep["version"] == "v1"
    assert rep["quality_gate"]["a"]["verdict"] == "未评定"
    assert rep["overlap_candidates"] == []
    assert rep["closest_pair_below_threshold"]["jaccard"] > 0
    assert "语义通道" in rep["overlap_note"]


def test_module_zero_network_ast():
    src = (Path(__file__).resolve().parents[1] / "scripts" / "skill_evaluation.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    banned = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            banned.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            banned.add(node.module.split(".")[0])
    assert not (banned & {"urllib", "requests", "http", "socket", "subprocess"}), banned
