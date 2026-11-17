# -*- coding: utf-8 -*-
"""技能评估 T3 闸门测试（PRD-492）。

运行：python3 -m pytest tests/test_prd492_t3_evaluation_gate.py -q
零网络、零外部依赖；报告与整改条目全合成占位。
"""
import ast
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from evaluation_gate import (  # noqa: E402
    append_audit,
    decide_and_audit,
    finalize,
    gate_check,
    load_ledger,
    load_remediation_file,
    main,
    parse_remediation_jsonl,
    route_product,
)

WHEN = "2026-11-17T10:00:00Z"


def _report(verdicts, versions=None):
    skills = []
    for sid in verdicts:
        entry = {"id": sid, "name": sid, "source": "skills/%s/SKILL.md" % sid}
        if versions and sid in versions:
            entry["version"] = versions[sid]
        skills.append(entry)
    return {
        "prd": "PRD-492", "repo": "mind-kit", "version": "v1",
        "date": "2026-11-17",
        "skills": skills,
        "quality_gate": {
            sid: {"verdict": v, "reason": "合成占位"}
            for sid, v in verdicts.items()
        },
    }


def _ledger(verdicts, remediation=None, versions=None):
    return load_ledger(_report(verdicts, versions), remediation or [])


def test_gate_passed_for_passing_skill():
    d = gate_check("a", _ledger({"a": "过关"}), as_of=WHEN)
    assert d["gate"] == "passed" and d["reason"] == "passed"
    assert d["version"] is None and d["version_asked"] is False
    assert route_product("a", _ledger({"a": "过关"}), as_of=WHEN)["channel"] == "可直接过"


def test_gate_blocks_failing_skill_product():
    # 验收要点：未过关技能的产物进不了下游，只能走人工审校。
    ledger = _ledger({"bad": "不过关"})
    d = gate_check("bad", ledger, as_of=WHEN)
    assert d["gate"] == "blocked" and d["reason"] == "failed"
    assert d["verdict"] == "不过关"
    route = route_product("bad", ledger, as_of=WHEN)
    assert route["channel"] == "人工审校" and route["gate"] == "blocked"


def test_gate_blocks_each_non_pass_verdict():
    cases = {
        "未过关": "failed",
        "待整改": "needs_remediation",
        "待复核": "pending_review",
        "未评定": "pending_review",
        "疑似失效": "pending_review",
    }
    for verdict, reason in cases.items():
        d = gate_check("s", _ledger({"s": verdict}), as_of=WHEN)
        assert d["gate"] == "blocked" and d["reason"] == reason, verdict


def test_gate_blocks_unknown_skill():
    d = gate_check("ghost", _ledger({"a": "过关"}), as_of=WHEN)
    assert d["gate"] == "blocked" and d["reason"] == "no_record"


def test_open_remediation_blocks_passing_skill():
    remediation = [{"skill": "a", "status": "待整改"}]
    d = gate_check("a", _ledger({"a": "过关"}, remediation), as_of=WHEN)
    assert d["gate"] == "blocked" and d["reason"] == "open_remediation"


def test_open_remediation_overlap_pair_blocks_both_sides():
    remediation = [{"skill": "a <-> b", "status": "待人工复核"}]
    for sid in ("a", "b"):
        d = gate_check(sid, _ledger({"a": "过关", "b": "过关"}, remediation),
                       as_of=WHEN)
        assert d["gate"] == "blocked" and d["reason"] == "open_remediation"


def test_handled_remediation_does_not_block():
    remediation = [{"skill": "a", "status": "已处理"}]
    d = gate_check("a", _ledger({"a": "过关"}, remediation), as_of=WHEN)
    assert d["gate"] == "passed"


def test_version_mismatch_blocks_old_pass():
    ledger = _ledger({"a": "过关"}, versions={"a": "1.2.0"})
    d = gate_check("a", ledger, as_of=WHEN, expected_version="1.3.0")
    assert d["gate"] == "blocked" and d["reason"] == "version_mismatch"
    assert d["version"] == "1.2.0" and d["expected_version"] == "1.3.0"


def test_version_asked_recorded_when_ledger_has_none():
    # T2 遗留口径：v1 报告无版本字段，闸门先按结论裁决，并在审计里
    # 记下被问到的版本，等报告补版本字段后再收紧。
    ledger = _ledger({"a": "过关"})  # v1：skills 条目无 version
    d = gate_check("a", ledger, as_of=WHEN, expected_version="1.0.0")
    assert d["gate"] == "passed"  # 按结论放行，不因无版本全拦
    assert d["version"] is None and d["version_asked"] is True
    assert d["expected_version"] == "1.0.0"


def test_finalize_hard_gate():
    ledger = _ledger({"a": "过关", "b": "不过关", "c": "过关"})
    out = finalize(["a", "b", "c"], ledger, as_of=WHEN)
    assert out["gate"] == "blocked"
    assert out["error_code"] == "GATE_NOT_ALL_PASSED"
    assert out["blocked_skills"] == ["b"]
    out2 = finalize(["a", "c"], ledger, as_of=WHEN)
    assert out2["gate"] == "passed" and out2["error_code"] is None


def test_audit_append_only_and_reproducible():
    ledger = _ledger({"a": "过关", "b": "不过关"})
    with tempfile.TemporaryDirectory() as d:
        audit = Path(d) / "gate_audit.jsonl"
        ref = {"path": "evaluation/skill-evaluation/report-2026-11-17.json",
               "date": "2026-11-17", "version": "v1"}
        decide_and_audit("a", ledger, audit, "tester", ref, as_of=WHEN)
        first = audit.read_text(encoding="utf-8")
        decide_and_audit("b", ledger, audit, "tester", ref, as_of=WHEN)
        lines = audit.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2
        assert first.splitlines()[0] == lines[0]  # 历史记录未被改写
        rec = json.loads(lines[1])
        assert rec["actor"] == "tester" and rec["timestamp"] == WHEN
        assert rec["report"] == ref and rec["skill_id"] == "b"
        assert rec["gate"] == "blocked" and rec["channel"] == "人工审校"
        assert rec["verdict"] == "不过关" and rec["reason"] == "failed"


def test_gate_never_touches_remediation_ledger():
    with tempfile.TemporaryDirectory() as d:
        ledger_file = Path(d) / "remediation.jsonl"
        ledger_file.write_text(
            json.dumps({"skill": "a", "status": "待整改"},
                       ensure_ascii=False) + "\n", encoding="utf-8")
        before = ledger_file.read_bytes()
        ledger = load_ledger(_report({"a": "过关"}),
                             load_remediation_file(ledger_file))
        gate_check("a", ledger, as_of=WHEN)
        decide_and_audit("a", ledger, Path(d) / "gate_audit.jsonl",
                         "tester", {"path": "r", "date": "d", "version": "v1"},
                         as_of=WHEN)
        assert ledger_file.read_bytes() == before  # 闸门只读清单，不改写


def test_invalid_report_and_bad_remediation_line_raise():
    try:
        load_ledger({"no_gate": True}, [])
    except ValueError as e:
        assert "quality_gate" in str(e)
    else:
        raise AssertionError("missing quality_gate should raise")
    try:
        parse_remediation_jsonl('{"skill": "a"}\n{bad json}\n')
    except json.JSONDecodeError:
        pass
    else:
        raise AssertionError("bad remediation line should raise, not drop")


def test_cli_exit_codes_allow_block_error(tmp_path):
    report = tmp_path / "report.json"
    report.write_text(json.dumps(_report({"a": "过关", "b": "不过关"}),
                                 ensure_ascii=False), encoding="utf-8")
    remediation = tmp_path / "remediation.jsonl"  # 不存在：视为 0 条
    audit = tmp_path / "gate_audit.jsonl"
    base = ["--report", str(report), "--remediation", str(remediation),
            "--audit", str(audit), "--actor", "cli-test", "--as-of", WHEN]
    assert main(base + ["--skill", "a"]) == 0
    assert main(base + ["--skill", "b"]) == 1
    assert main(base + ["--skill", "ghost"]) == 1  # 无记录照样拦
    bad = tmp_path / "bad.json"
    bad.write_text("{}", encoding="utf-8")
    assert main(["--report", str(bad), "--skill", "a",
                 "--remediation", str(remediation),
                 "--audit", str(audit)]) == 2
    recs = [json.loads(x) for x in audit.read_text(encoding="utf-8").splitlines()]
    assert [r["skill_id"] for r in recs] == ["a", "b", "ghost"]


def test_module_zero_network_ast():
    src = (Path(__file__).resolve().parents[1] / "scripts"
           / "evaluation_gate.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    banned = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            banned.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            banned.add(node.module.split(".")[0])
    assert not (banned & {"urllib", "requests", "http", "socket",
                          "subprocess"}), banned
