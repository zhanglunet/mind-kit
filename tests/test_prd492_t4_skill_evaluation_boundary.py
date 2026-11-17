# -*- coding: utf-8 -*-
"""技能评估 T4 划界断言（PRD-492）。

按 T1 设计稿 docs/plans/2026-11-17-prd-492-mindkit-skill-evaluation-design.md
§四边界表逐条钉死：
  - 评估与闸门模块跟邻居模块双向零导入（§四 5 行邻居全列清）；
  - 评估不越界：不审产物（PRD-433 评审流水线的事）、不审过程
    （PRD-456 监督台的事）、不改共建流程（PRD-410）、不验知识
    （PRD-387）、不给单个 skill 写测试（PRD-012/022/034/037）；
  - T1 §五红线逐条钉死；
  - 词表封闭：评估结论 / 拦因 / 通道 / 整改类型与状态只能取设计稿
    定的封闭集合；
  - T3 口径决策各补一例断言：放行当且仅当“过关”且无未处理整改项；
    CLI 退出码 0/1/2 的 fail-closed 语义；版本字段缺失时按结论裁决
    并在审计里记 version_asked。

只断言，不动 scripts/ 下任何生产代码。运行：
  python3 -m pytest tests/test_prd492_t4_skill_evaluation_boundary.py -q
零网络、零外部依赖；报告与整改条目全合成占位。
"""
import ast
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import skill_evaluation as se  # noqa: E402
import evaluation_gate as eg  # noqa: E402
from evaluation_gate import (  # noqa: E402
    BLOCKED_REASONS, HANDLED_REMEDIATION_STATUSES, finalize, gate_check,
    load_ledger, main as gate_main, route_product,
)

WHEN = "2026-11-17T10:00:00Z"
ROOT = Path(__file__).resolve().parents[1]

# T1 §四边界表里的邻居模块（按行列清）。
NEIGHBOR_MODULES = [
    "knowledge_review_pipeline.py",       # PRD-433 评审流水线
    "knowledge_review_pipeline_gates.py",  # PRD-433 闸门
    "knowledge_collab_session.py",         # PRD-410 知识共建会话
    "knowledge_collab_session_gates.py",   # PRD-410 闸门
    "knowledge_verify_bench.py",           # PRD-387 入库知识验证台
    "knowledge_verify_bench_gates.py",     # PRD-387 闸门
    "knowledge_supervision_bench.py",      # PRD-456 监督台
    "knowledge_supervision_gate.py",       # PRD-456 闸门
    "knowledge_supervision_acceptance.py",  # PRD-456 验收
    "build-skill-package.py",              # PRD-012/022/034/037 单个 skill 打包
]
# “邻居面无评估符号”那条断言排除监督台自身三个模块：监督闸门的
# gate() 是它自己的闸门（不是评估闸门 gate_check），排开才是对的。
NEIGHBOR_MODULES_NO_SUPERVISION = [
    m for m in NEIGHBOR_MODULES
    if not m.startswith("knowledge_supervision")
]
EVAL_MODULES = ["skill_evaluation.py", "evaluation_gate.py"]


def _module_path(name):
    return ROOT / "scripts" / name


def _imports_of(path):
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    return imported


def _identifiers_of(path):
    """代码标识符（小写）：定义名/参数名/Name/Attribute；字符串字面量不算。"""
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            names.add(node.name.lower())
        elif isinstance(node, ast.arg):
            names.add(node.arg.lower())
        elif isinstance(node, ast.Name):
            names.add(node.id.lower())
        elif isinstance(node, ast.Attribute):
            names.add(node.attr.lower())
    return names


def _string_literals_of(path):
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    return [n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)]


def _eval_identifiers():
    merged = set()
    for mod in EVAL_MODULES:
        merged |= _identifiers_of(_module_path(mod))
    return merged


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


def _skill(sid, text):
    return {"id": sid, "name": sid, "text": text,
            "source": "skills/%s/SKILL.md" % sid}


def _error_rate_measurements(drop=0.28, worst=0.02, rounds=("过关", "过关"),
                            reproducible=True):
    return {
        "baseline_error_rate": 0.25,
        "skill_error_rate": 0.25 * (1 - drop),
        "category_worsening_pp": {"事实": worst},
        "rounds": list(rounds),
        "control_reproducible": reproducible,
    }


class TestModuleIsolation:
    def test_eval_gate_never_import_neighbors(self):
        """§四：评估与闸门模块不导入任何邻居模块（双向零导入的一边）。"""
        banned = {
            "knowledge_review_pipeline", "knowledge_review_pipeline_gates",
            "knowledge_collab_session", "knowledge_collab_session_gates",
            "knowledge_verify_bench", "knowledge_verify_bench_gates",
            "knowledge_supervision_bench", "knowledge_supervision_gate",
            "knowledge_supervision_acceptance", "build_skill_package",
        }
        for mod in EVAL_MODULES:
            imported = _imports_of(_module_path(mod))
            hits = sorted(imported & banned)
            assert hits == [], f"{mod} 导入了邻居：{hits}"
            # build-skill-package.py 带连字符，名字上就 import 不了；
            # 再扫一遍 import 行原文，确认连它的文件名都没出现。
            src = _module_path(mod).read_text(encoding="utf-8")
            for line in src.splitlines():
                s = line.strip()
                if s.startswith(("import ", "from ")):
                    assert "skill-package" not in s, f"{mod}: {s}"

    def test_neighbors_never_import_eval(self):
        """§四：邻居模块不导入评估或闸门模块（双向零导入的另一边）。"""
        for mod in NEIGHBOR_MODULES:
            imported = _imports_of(_module_path(mod))
            hits = sorted(imported & {"skill_evaluation", "evaluation_gate"})
            assert hits == [], f"{mod} 导入了评估模块：{hits}"

    def test_neighbors_have_no_eval_symbols(self):
        """§四：邻居面无评估符号——邻居代码里没有评估/闸门的标识符。
        监督台自身三个模块排开（见文件头注释：监督闸门的 gate() 是它
        自己的闸门，不是评估闸门 gate_check）。"""
        banned = ("skill_evaluation", "evaluation_gate", "gate_check",
                  "quality_gate", "detect_overlap", "run_evaluation",
                  "remediation")
        for mod in NEIGHBOR_MODULES_NO_SUPERVISION:
            names = _identifiers_of(_module_path(mod))
            for word in banned:
                hits = sorted(n for n in names if word in n)
                assert hits == [], f"{mod} 出现评估符号 {word}：{hits}"

    def test_eval_gate_stdlib_only_pinned(self):
        """标准库-only 钉值：两模块的导入集合钉死，全是标准库。"""
        assert _imports_of(_module_path("skill_evaluation.py")) == {
            "argparse", "json", "math", "pathlib", "re", "sys"}
        assert _imports_of(_module_path("evaluation_gate.py")) == {
            "argparse", "datetime", "json", "os", "pathlib", "sys"}

    def test_modules_zero_network_ast(self):
        """零网络零子进程：两模块静态导入里无网络/子进程模块。"""
        for mod in EVAL_MODULES:
            banned = _imports_of(_module_path(mod))
            assert not (banned & {"urllib", "requests", "http", "socket",
                                  "subprocess"}), (mod, banned)

    def test_modules_have_no_url_scheme_strings(self):
        """占位断言只断 http:// 与 https://，不断裸 http——裸 http 会
        误伤零网络测试自己的 banned 集（它含 "http" 这个导入名）。"""
        for mod in EVAL_MODULES:
            for s in _string_literals_of(_module_path(mod)):
                assert "http://" not in s, f"{mod} 含 http://：{s[:60]}"
                assert "https://" not in s, f"{mod} 含 https://：{s[:60]}"


class TestEvalDoesNotJudgeProducts:
    def test_eval_has_no_product_review_identifiers(self):
        """§四 PRD-433 行：评估不审产物——评估模块无评审/产物类标识符。"""
        names = _identifiers_of(_module_path("skill_evaluation.py"))
        for word in ("review", "pipeline", "approve", "reject", "product"):
            hits = sorted(n for n in names if word in n)
            assert hits == [], f"评估模块出现 {word} 相关标识符：{hits}"

    def test_gate_only_routes_never_reviews(self):
        """§四 PRD-433 行：闸门只分流产物走哪条通道，不审产物、不批产物。
        route_product 只回裁决四件套，不含任何评审结论字段。"""
        names = _identifiers_of(_module_path("evaluation_gate.py"))
        for word in ("review_pipeline", "knowledge_review", "approve",
                     "reject"):
            hits = sorted(n for n in names if word in n)
            assert hits == [], f"闸门模块出现 {word} 相关标识符：{hits}"
        out = route_product("a", _ledger({"a": "过关"}), as_of=WHEN)
        assert set(out) == {"skill_id", "channel", "gate", "reason",
                            "verdict"}
        assert out["channel"] == "可直接过"
        blocked = route_product("a", _ledger({"a": "不过关"}), as_of=WHEN)
        assert set(blocked) == {"skill_id", "channel", "gate", "reason",
                                "verdict"}
        assert blocked["channel"] == "人工审校"
        # 纯函数：同一账本两次裁决结果一致，账本本身不动。
        ledger = _ledger({"a": "过关"})
        before = copy.deepcopy(ledger)
        assert route_product("a", ledger, as_of=WHEN) == \
            route_product("a", ledger, as_of=WHEN)
        assert ledger == before


class TestEvalDoesNotJudgeProcess:
    def test_eval_has_no_process_identifiers(self):
        """§四 PRD-456 行：评估不审 agent 干活过程——两模块无过程类标识符。"""
        names = _eval_identifiers()
        for word in ("supervis", "agent", "session", "collab", "transcript",
                     "process", "cowrite", "coedit"):
            hits = sorted(n for n in names if word in n)
            assert hits == [], f"出现 {word} 相关标识符：{hits}"

    def test_eval_has_no_collab_or_wiki_identifiers(self):
        """§四 PRD-410 行 + 载体边界：不改共建流程、不碰 Wiki 载体。"""
        names = _eval_identifiers()
        for word in ("collab", "wiki", "store"):
            hits = sorted(n for n in names if word in n)
            assert hits == [], f"出现 {word} 相关标识符：{hits}"


class TestRedLines:
    def test_borrowed_repos_zero_symbols(self):
        """§五：只借鉴思路，不复用代码——借鉴仓零符号（仅代码标识符扫描，
        docstring 提及不算）。"""
        names = _eval_identifiers()
        for word in ("skillevaluator", "bughunter", "stitch"):
            hits = sorted(n for n in names if word in n)
            assert hits == [], f"出现借鉴仓符号 {word}：{hits}"

    def test_eval_never_deletes(self):
        """§五：评估只进整改清单，绝不直接删技能——无删类标识符、无 del
        语句；append-only 追加后旧账逐字节不动。"""
        for mod in EVAL_MODULES:
            names = _identifiers_of(_module_path(mod))
            for word in ("delete", "remove", "unlink", "rmtree"):
                hits = sorted(n for n in names if word in n)
                assert hits == [], f"{mod} 出现删类标识符 {word}：{hits}"
            tree = ast.parse(_module_path(mod).read_text(encoding="utf-8"))
            assert not [n for n in ast.walk(tree)
                        if isinstance(n, ast.Delete)], f"{mod} 有 del 语句"

    def test_append_remediation_keeps_history_byte_identical(self, tmp_path):
        """§五：整改清单 append-only——追加只加行，旧行逐字节不动。"""
        ledger_file = tmp_path / "remediation.jsonl"
        old_lines = [
            json.dumps({"skill": "a", "status": "待整改"},
                       ensure_ascii=False),
            json.dumps({"skill": "b", "status": "待人工复核"},
                       ensure_ascii=False),
        ]
        ledger_file.write_text("\n".join(old_lines) + "\n", encoding="utf-8")
        se.append_remediation(
            ledger_file, [{"skill": "c", "status": "待整改"}])
        lines = ledger_file.read_text(encoding="utf-8").splitlines()
        assert lines[:2] == old_lines
        assert len(lines) == 3
        assert json.loads(lines[2])["skill"] == "c"

    def test_no_synthetic_question_construction(self):
        """§五：评测题必须有真实案例证据来源——评估模块不造题：无造题类
        标识符；评估报告里无评测题/题库字段（造题是 T5 的事，本模块不做）。"""
        names = _eval_identifiers()
        for word in ("question", "exam", "benchmark"):
            hits = sorted(n for n in names if word in n)
            assert hits == [], f"出现造题类标识符 {word}：{hits}"
        report = se.run_evaluation(
            [_skill("a", "教备份的技能（占位）")],
            {"a": _error_rate_measurements()},
            "error-rate", "PRD-492", "mind-kit")
        assert not (set(report) & {"questions", "test_set", "exam",
                                   "question_bank"})

    def test_quality_gate_thresholds_pinned(self):
        """§五 + §二：质量门阈值由 T1 设计评审定——阈值常量钉死 T1 §二的值，
        不拍脑袋改。"""
        assert se.ERROR_DROP_PASS == 0.20
        assert se.CATEGORY_WORSEN_LIMIT == 0.05
        assert se.TEXT_THRESHOLD == 0.70
        assert se.SEMANTIC_THRESHOLD == 0.85
        assert se.MISS_WORSEN_LIMIT == 0.02
        assert se.ABS_ERROR_LIMIT == 0.05
        assert se.TRIGGER_FLOOR == 0.10

    def test_report_skills_carry_source_and_evidence(self):
        """§五：入库知识必须可溯源，评估不降低溯源要求——报告里的技能
        条条带来源；重叠候选带共享词证据；整改条目带证据。"""
        skills = [
            _skill("a", "教备份与恢复的技能 备份 恢复 快照（占位）"),
            _skill("b", "教备份与恢复的技能 备份 恢复 快照（占位）"),
        ]
        report = se.run_evaluation(
            skills, {"a": _error_rate_measurements(drop=-0.1),
                     "b": _error_rate_measurements()},
            "error-rate", "PRD-492", "mind-kit")
        assert all(s.get("source") for s in report["skills"])
        assert report["overlap_candidates"]
        cand = report["overlap_candidates"][0]
        assert cand["shared_tokens"]
        assert cand["semantic"].startswith("未跑")
        assert all(e.get("evidence") for e in
                   report["remediation_new_entries"])

    def test_remediation_vocab_closed(self):
        """整改清单词表封闭：类型与状态只能取评估器写的那几个值。"""
        skills = [_skill("a", "教备份的技能（占位）"),
                  _skill("b", "教备份的技能（占位）")]
        report = se.run_evaluation(
            skills, {"a": _error_rate_measurements(drop=-0.1),
                     "b": _error_rate_measurements()},
            "error-rate", "PRD-492", "mind-kit")
        types = {e["type"] for e in report["remediation_new_entries"]}
        statuses = {e["status"] for e in report["remediation_new_entries"]}
        assert types <= {"失效/待整改", "疑似失效", "疑似重叠"}
        assert statuses <= {"待整改", "待人工复核"}
        assert set(HANDLED_REMEDIATION_STATUSES) == {
            "已处理", "已关闭", "已复核", "已下线"}


class TestClosedVocab:
    def test_eval_verdict_vocab_closed(self):
        """词表封闭：评估结论只能取设计稿定的 7 个值，出现集合外的值即失败。"""
        seen = set()
        # error-rate 变体四档。
        seen.add(se.quality_gate_error_rate(
            _error_rate_measurements())[0])
        seen.add(se.quality_gate_error_rate(
            _error_rate_measurements(drop=0.10))[0])
        seen.add(se.quality_gate_error_rate(
            _error_rate_measurements(drop=-0.10))[0])
        seen.add(se.quality_gate_error_rate(
            _error_rate_measurements(rounds=("过关", "待整改")))[0])
        # three-metric 变体三档。
        seen.add(se.quality_gate_three_metric({
            "baseline_error_rate": 0.25, "skill_error_rate": 0.03,
            "baseline_miss_rate": 0.05, "skill_miss_rate": 0.05,
            "trigger_rate": 0.5})[0])
        seen.add(se.quality_gate_three_metric({
            "baseline_error_rate": 0.25, "skill_error_rate": 0.30,
            "baseline_miss_rate": 0.05, "skill_miss_rate": 0.05,
            "trigger_rate": 0.5})[0])
        seen.add(se.quality_gate_three_metric({
            "baseline_error_rate": 0.25, "skill_error_rate": 0.03,
            "baseline_miss_rate": 0.05, "skill_miss_rate": 0.05,
            "trigger_rate": 0.05})[0])
        # 无对照数据：未评定。
        report = se.run_evaluation(
            [_skill("a", "教备份的技能（占位）")], {},
            "error-rate", "PRD-492", "mind-kit")
        seen.add(report["quality_gate"]["a"]["verdict"])
        assert seen == {"过关", "待整改", "不过关", "待复核",
                        "未评定", "未过关", "疑似失效"}
        # 重叠只判“疑似”，结论词钉死一句话。
        pairs = se.detect_overlap([
            _skill("a", "教备份与恢复的技能 备份 恢复 快照（占位）"),
            _skill("b", "教备份与恢复的技能 备份 恢复 快照（占位）"),
        ])
        assert len(pairs) == 1
        assert pairs[0]["verdict"] == "疑似重叠（待人工复核）"

    def test_gate_reason_and_channel_vocab_closed(self):
        """词表封闭：拦因与通道只能取闸门定的封闭集合。"""
        assert set(BLOCKED_REASONS) == {
            "no_record", "failed", "needs_remediation", "pending_review",
            "open_remediation", "version_mismatch", "invalid_record"}
        assert set(eg.VERDICT_REASONS) <= {
            "不过关", "未过关", "待整改", "待复核", "未评定", "疑似失效"}
        assert "过关" not in eg.VERDICT_REASONS
        channels = {
            route_product("a", _ledger({"a": "过关"}),
                          as_of=WHEN)["channel"],
            route_product("a", _ledger({"a": "不过关"}),
                          as_of=WHEN)["channel"],
        }
        assert channels == {"可直接过", "人工审校"}


class TestT3Decisions:
    def test_pass_iff_passed_and_no_open_remediation(self):
        """T3 口径：放行当且仅当结论“过关”且无未处理整改项。"""
        assert gate_check("a", _ledger({"a": "过关"}),
                          as_of=WHEN)["gate"] == "passed"
        # 各档非过关结论一律拦下，拦因按映射表。
        expected = {
            "不过关": "failed", "未过关": "failed",
            "待整改": "needs_remediation", "待复核": "pending_review",
            "未评定": "pending_review", "疑似失效": "pending_review",
        }
        for verdict, reason in expected.items():
            d = gate_check("a", _ledger({"a": verdict}), as_of=WHEN)
            assert d["gate"] == "blocked" and d["reason"] == reason, verdict
        # 账本里没这技能：拦下，no_record。
        assert gate_check("ghost", _ledger({"a": "过关"}),
                          as_of=WHEN)["reason"] == "no_record"
        # 集合外的结论：拦下，invalid_record。
        d = gate_check("a", _ledger({"a": "胡说"}), as_of=WHEN)
        assert d["gate"] == "blocked" and d["reason"] == "invalid_record"
        # 过关但有未处理整改项：拦下，open_remediation。
        d = gate_check("a", _ledger(
            {"a": "过关"},
            remediation=[{"skill": "a", "status": "待整改"}]), as_of=WHEN)
        assert d["gate"] == "blocked" and d["reason"] == "open_remediation"
        # 同一条已处理：放行。
        d = gate_check("a", _ledger(
            {"a": "过关"},
            remediation=[{"skill": "a", "status": "已处理"}]), as_of=WHEN)
        assert d["gate"] == "passed"

    def test_cli_exit_codes_fail_closed(self, tmp_path):
        """T3 口径：CLI 退出码 0 放行 / 1 拦截 / 2 报告无效——拿不到
        有效报告就拦（fail-closed），没有默认通过。"""
        report_path = tmp_path / "report.json"
        remediation_path = tmp_path / "remediation.jsonl"
        audit_path = tmp_path / "gate_audit.jsonl"
        remediation_path.write_text("", encoding="utf-8")

        def run_cli(verdict):
            report_path.write_text(
                json.dumps(_report({"a": verdict}), ensure_ascii=False),
                encoding="utf-8")
            return gate_main(["--report", str(report_path), "--skill", "a",
                              "--remediation", str(remediation_path),
                              "--audit", str(audit_path),
                              "--actor", "t4-boundary",
                              "--as-of", WHEN])

        assert run_cli("过关") == 0
        assert run_cli("不过关") == 1
        report_path.write_text("{bad json", encoding="utf-8")
        assert gate_main(["--report", str(report_path), "--skill", "a",
                          "--remediation", str(remediation_path),
                          "--audit", str(audit_path),
                          "--actor", "t4-boundary"]) == 2
        assert gate_main(["--report", str(tmp_path / "不存在.json"),
                          "--skill", "a",
                          "--remediation", str(remediation_path),
                          "--audit", str(audit_path),
                          "--actor", "t4-boundary"]) == 2

    def test_version_missing_judges_by_verdict_and_records_asked(self):
        """T3 口径：版本字段缺失时按结论裁决，并在审计里记 version_asked；
        账本有版本且不一致即拦下。"""
        d = gate_check("a", _ledger({"a": "过关"}), as_of=WHEN,
                       expected_version="v9")
        assert d["gate"] == "passed"
        assert d["version_asked"] is True
        assert d["expected_version"] == "v9"
        d = gate_check("a", _ledger({"a": "过关"}, versions={"a": "v1"}),
                       as_of=WHEN, expected_version="v2")
        assert d["gate"] == "blocked"
        assert d["reason"] == "version_mismatch"
        d = gate_check("a", _ledger({"a": "过关"}, versions={"a": "v1"}),
                       as_of=WHEN, expected_version="v1")
        assert d["gate"] == "passed"
        assert d["version_asked"] is False

    def test_finalize_hard_gate_one_block_vetoes_all(self):
        """T3 口径：整批硬闸门——一批里有一个被拦，整批拒绝。"""
        out = finalize(["a", "b"], _ledger({"a": "过关", "b": "待整改"}),
                       as_of=WHEN)
        assert out["gate"] == "blocked"
        assert out["error_code"] == "GATE_NOT_ALL_PASSED"
        assert out["blocked_skills"] == ["b"]
        out = finalize(["a", "b"], _ledger({"a": "过关", "b": "过关"}),
                       as_of=WHEN)
        assert out["gate"] == "passed"
        assert out["error_code"] is None
