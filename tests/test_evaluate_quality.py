"""evaluate_quality.py 的行为测试(P0-2a):认知边界 grep 断言。
case = {path, required_tokens[], forbidden_tokens[]};required 缺失或 forbidden 出现即失败;
文件缺失默认失败,--allow-missing 降级为跳过(容器里 vault 软链缺席时用)。
"""
import sys
import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RUNNER = REPO / "scripts" / "evaluate_quality.py"


def _run(*args):
    return subprocess.run([sys.executable, str(RUNNER), *args],
                          capture_output=True, text=True, cwd=str(REPO))


def _setup(tmp_path: Path):
    (tmp_path / "卡片.md").write_text(
        "营收同比下降 5.2%。管理层提出转型目标,但不据此推断转型已经成功。",
        encoding="utf-8")
    return tmp_path


def _cases(tmp_path: Path, cases) -> Path:
    p = tmp_path / "quality.json"
    p.write_text(json.dumps(
        {"schema_version": "eval-quality-1", "cases": cases}, ensure_ascii=False),
        encoding="utf-8")
    return p


def test_pass_when_required_present_forbidden_absent(tmp_path):
    _setup(tmp_path)
    f = _cases(tmp_path, [{
        "id": "q1", "path": "卡片.md",
        "required_tokens": ["下降 5.2%", "不据此推断转型已经成功"],
        "forbidden_tokens": ["收入实现增长", "转型已经成功。管理层确认"],
    }])
    r = _run(str(f), "--base", str(tmp_path), "--json")
    assert r.returncode == 0, r.stdout + r.stderr


def test_fail_when_required_missing(tmp_path):
    _setup(tmp_path)
    f = _cases(tmp_path, [{
        "id": "q2", "path": "卡片.md",
        "required_tokens": ["这句话根本不存在"], "forbidden_tokens": [],
    }])
    r = _run(str(f), "--base", str(tmp_path), "--json")
    assert r.returncode == 1
    out = json.loads(r.stdout)
    assert out["failed"] == 1
    assert "这句话根本不存在" in json.dumps(out["results"], ensure_ascii=False)


def test_fail_when_forbidden_present(tmp_path):
    _setup(tmp_path)
    f = _cases(tmp_path, [{
        "id": "q3", "path": "卡片.md",
        "required_tokens": [], "forbidden_tokens": ["营收同比下降"],
    }])
    r = _run(str(f), "--base", str(tmp_path), "--json")
    assert r.returncode == 1


def test_missing_file_fails_by_default_skips_with_flag(tmp_path):
    f = _cases(tmp_path, [{
        "id": "q4", "path": "不存在的页.md",
        "required_tokens": ["x"], "forbidden_tokens": [],
    }])
    r = _run(str(f), "--base", str(tmp_path), "--json")
    assert r.returncode == 1
    r2 = _run(str(f), "--base", str(tmp_path), "--allow-missing", "--json")
    assert r2.returncode == 0
    assert json.loads(r2.stdout)["skipped"] == 1


def test_forbidden_substring_of_required_not_false_positive(tmp_path):
    # 评审确认问题:README 示范里 forbidden(「转型已经成功」)是 required 限定语
    # (「不据此推断转型已经成功」)的子串——裸子串匹配会永不可满足。
    # 修法:先把 required 的出现位置遮蔽,再查 forbidden。
    (tmp_path / "卡.md").write_text("管理层提出目标,但不据此推断转型已经成功。", encoding="utf-8")
    f = _cases(tmp_path, [{
        "id": "m1", "path": "卡.md",
        "required_tokens": ["不据此推断转型已经成功"],
        "forbidden_tokens": ["转型已经成功"],
    }])
    r = _run(str(f), "--base", str(tmp_path), "--json")
    assert r.returncode == 0, "限定语内出现的 forbidden 子串不应误报:" + r.stdout


def test_forbidden_standalone_occurrence_still_fails(tmp_path):
    # 但 forbidden 在限定语之外独立出现时,仍必须失败
    (tmp_path / "卡.md").write_text(
        "不据此推断转型已经成功。……总结:转型已经成功,业绩大增。", encoding="utf-8")
    f = _cases(tmp_path, [{
        "id": "m2", "path": "卡.md",
        "required_tokens": ["不据此推断转型已经成功"],
        "forbidden_tokens": ["转型已经成功"],
    }])
    r = _run(str(f), "--base", str(tmp_path), "--json")
    assert r.returncode == 1, "独立出现的过度声明必须被抓住:" + r.stdout


def test_zero_cases_is_usage_error(tmp_path):
    # 评审确认问题:cases 键拼错/为空 → 0 条断言却 exit 0,门禁假绿。应按用法错误 exit 2。
    f = _cases(tmp_path, [])
    r = _run(str(f), "--base", str(tmp_path), "--json")
    assert r.returncode == 2, f"0 个 case 应 exit 2,实际 {r.returncode}"


def test_committed_quality_sample_passes():
    sample = REPO / "evaluation" / "fixtures" / "quality_sample" / "cases.json"
    assert sample.exists(), "evaluation/fixtures/quality_sample/cases.json 应存在"
    r = _run(str(sample), "--base",
             str(REPO / "evaluation" / "fixtures" / "quality_sample"), "--json")
    assert r.returncode == 0, r.stdout + r.stderr
