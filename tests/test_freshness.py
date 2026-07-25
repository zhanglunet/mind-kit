"""freshness.py 轻量保鲜模型的行为测试(P1-3,FR-LNT-07)。
契约:
- 扫 <vault>/_wiki/outputs/*.md + material/*/*.md 的 frontmatter;
- volatility 三档预设半衰期 high=30 / medium=90 / low=365;half_life_days 显式值优先;
- freshness_factor = 0.5^(距 last_confirmed 天数 / half_life);
- 默认报 factor ≤ 0.5(过一个半衰期),factor ≤ 0.25 标急;**只提示,不改任何页面**;
- 无保鲜字段的页面静默跳过(不报错、不出现在报告);
- --confirm <相对路径> 显式盖 last_confirmed=今天,其余内容原样保留。
"""
import json
import subprocess
from datetime import date, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CLI = REPO / "scripts" / "freshness.py"


def _run(vault: Path, *args):
    return subprocess.run(["python3", str(CLI), "--vault", str(vault), *args],
                          capture_output=True, text=True, cwd=str(REPO))


def _page(vault: Path, rel: str, fm: dict, body="正文。"):
    p = vault / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    lines = ["---"] + [f"{k}: {v}" for k, v in fm.items()] + ["---", "", body]
    p.write_text("\n".join(lines), encoding="utf-8")
    return p


def _days_ago(n: int) -> str:
    return (date.today() - timedelta(days=n)).isoformat()


def test_stale_page_reported_with_factor(tmp_path):
    # half_life 30 天、60 天没确认 → factor = 0.25,应报且标急
    _page(tmp_path, "_wiki/outputs/旧分析.md",
          {"title": "旧分析", "half_life_days": 30, "last_confirmed": _days_ago(60)})
    r = _run(tmp_path, "--json")
    assert r.returncode == 0, r.stdout + r.stderr
    out = json.loads(r.stdout)
    assert len(out["stale"]) == 1
    row = out["stale"][0]
    assert row["path"].endswith("旧分析.md")
    assert abs(row["factor"] - 0.25) < 0.01
    assert row["urgent"] is True


def test_fresh_page_not_reported(tmp_path):
    _page(tmp_path, "_wiki/outputs/新页.md",
          {"half_life_days": 90, "last_confirmed": _days_ago(10)})   # factor≈0.93
    out = json.loads(_run(tmp_path, "--json").stdout)
    assert out["stale"] == []
    assert out["tracked"] == 1


def test_volatility_presets_and_explicit_override(tmp_path):
    # medium 预设 90 天:100 天未确认 → factor<0.5 报;显式 half_life_days 覆盖预设
    _page(tmp_path, "material/frameworks/框架页.md",
          {"volatility": "medium", "last_confirmed": _days_ago(100)})
    _page(tmp_path, "material/data/数据页.md",
          {"volatility": "medium", "half_life_days": 365, "last_confirmed": _days_ago(100)})
    out = json.loads(_run(tmp_path, "--json").stdout)
    paths = [x["path"] for x in out["stale"]]
    assert any("框架页" in p for p in paths), "medium 预设 90 天应报"
    assert not any("数据页" in p for p in paths), "显式 365 天不应报"


def test_pages_without_fields_silently_skipped(tmp_path):
    _page(tmp_path, "_wiki/outputs/无字段.md", {"title": "无字段"})
    (tmp_path / "material" / "quotes").mkdir(parents=True)
    (tmp_path / "material" / "quotes" / "裸文件.md").write_text("没有 frontmatter", encoding="utf-8")
    r = _run(tmp_path, "--json")
    assert r.returncode == 0, "无字段/无 fm 页面不得报错:" + r.stderr
    out = json.loads(r.stdout)
    assert out["tracked"] == 0 and out["stale"] == []


def test_missing_last_confirmed_treated_as_needs_review(tmp_path):
    # 声明了 volatility 却没写 last_confirmed:视为待复核(报出来),而非静默跳过
    _page(tmp_path, "_wiki/outputs/漏日期.md", {"volatility": "high"})
    out = json.loads(_run(tmp_path, "--json").stdout)
    assert len(out["stale"]) == 1
    assert out["stale"][0]["factor"] is None


def test_confirm_stamps_today_and_preserves_content(tmp_path):
    p = _page(tmp_path, "_wiki/outputs/待确认页.md",
              {"title": "待确认页", "half_life_days": 30, "last_confirmed": _days_ago(60)},
              body="重要正文,不得被动。")
    r = _run(tmp_path, "--confirm", "_wiki/outputs/待确认页.md")
    assert r.returncode == 0, r.stdout + r.stderr
    text = p.read_text(encoding="utf-8")
    assert f"last_confirmed: {date.today().isoformat()}" in text
    assert "重要正文,不得被动。" in text
    assert "half_life_days: 30" in text
    out = json.loads(_run(tmp_path, "--json").stdout)
    assert out["stale"] == []                       # 确认后不再报


def test_confirm_rejects_page_outside_scope(tmp_path):
    # 只允许确认 LLM 领地(outputs/material)的页面,不得去戳引擎领地
    _page(tmp_path, "_wiki/concepts/概念页.md", {"half_life_days": 30})
    r = _run(tmp_path, "--confirm", "_wiki/concepts/概念页.md")
    assert r.returncode != 0, "concepts 是引擎领地,--confirm 应拒绝"


def test_report_only_never_modifies_pages(tmp_path):
    p = _page(tmp_path, "_wiki/outputs/只读检查.md",
              {"half_life_days": 30, "last_confirmed": _days_ago(90)})
    before = p.read_bytes()
    _run(tmp_path)
    _run(tmp_path, "--json")
    assert p.read_bytes() == before, "报告模式不得改动任何页面"


def test_confirm_rejects_dotdot_escape_and_prefix_collision(tmp_path):
    # 评审 F1 HIGH / F2:`..` 穿透与前缀碰撞都必须被拒,且目标文件不被改
    concept = _page(tmp_path, "_wiki/concepts/概念页.md", {"half_life_days": 30})
    victim = tmp_path.parent / "victim.md"
    victim.write_text("---\nhalf_life_days: 30\n---\nvault 外文件", encoding="utf-8")
    sibling = _page(tmp_path, "material-old/x.md", {"half_life_days": 30})
    for rel, target in (("material/../_wiki/concepts/概念页.md", concept),
                        (f"material/../../{victim.name}", victim),
                        ("material-old/x.md", sibling)):
        before = target.read_bytes()
        r = _run(tmp_path, "--confirm", rel)
        assert r.returncode != 0, f"{rel} 应被拒"
        assert target.read_bytes() == before, f"{rel} 的目标不得被改动"


def test_confirm_only_within_scan_face(tmp_path):
    # 评审 F8:confirm 作用面必须与扫描面一致——决策记录子目录、六类外/更深层 material 都拒
    deep = _page(tmp_path, "material/cases/2026/深层.md", {"half_life_days": 30})
    dec = _page(tmp_path, "_wiki/outputs/decisions/DEC-1.md", {"half_life_days": 30})
    for rel, target in (("material/cases/2026/深层.md", deep),
                        ("_wiki/outputs/decisions/DEC-1.md", dec)):
        before = target.read_bytes()
        assert _run(tmp_path, "--confirm", rel).returncode != 0, f"{rel} 不在扫描面,应拒"
        assert target.read_bytes() == before


def test_confirm_refuses_hr_started_doc(tmp_path):
    # 评审 F3:以 --- 水平线开头的无 frontmatter 文档,不得被误认成 fm 而把章盖进正文
    p = tmp_path / "_wiki" / "outputs" / "横线开头.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("---\n\n## 引言\n\n一段正文。\n\n---\n\n结尾。\n", encoding="utf-8")
    before = p.read_bytes()
    r = _run(tmp_path, "--confirm", "_wiki/outputs/横线开头.md")
    assert r.returncode != 0, "无保鲜声明/伪 fm 的页面应拒绝盖章"
    assert p.read_bytes() == before, "内容不得被腐蚀"


def test_future_last_confirmed_reported(tmp_path):
    # 评审 F4:last_confirmed 在未来(年份笔误)不得静默当"永远新鲜",应报待复核
    _page(tmp_path, "_wiki/outputs/未来页.md",
          {"half_life_days": 30, "last_confirmed": (date.today() + timedelta(days=3650)).isoformat()})
    out = json.loads(_run(tmp_path, "--json").stdout)
    assert len(out["stale"]) == 1
    assert "未来" in out["stale"][0]["note"]


def test_bad_half_life_fallback_and_report(tmp_path):
    # 评审 F5:显式 half_life 写坏但有 volatility → 回落预设;两者都坏 → 报"写坏"而非静默除名
    _page(tmp_path, "_wiki/outputs/回落页.md",
          {"volatility": "high", "half_life_days": "oops", "last_confirmed": _days_ago(60)})
    _page(tmp_path, "_wiki/outputs/全坏页.md",
          {"half_life_days": "-5", "last_confirmed": _days_ago(1)})
    out = json.loads(_run(tmp_path, "--json").stdout)
    assert out["tracked"] == 2, "两页都声明了保鲜,都应在册"
    paths = {x["path"]: x for x in out["stale"]}
    assert any("回落页" in p for p in paths), "回落 high=30 天、60 天未确认应报"
    bad = next(x for p, x in paths.items() if "全坏页" in p)
    assert "写坏" in bad["note"]


def test_quoted_date_parsed(tmp_path):
    # 评审 F6:引号包裹的日期(合法 YAML)不得误报"缺 last_confirmed"
    _page(tmp_path, "_wiki/outputs/引号日期.md",
          {"half_life_days": 90, "last_confirmed": f'"{_days_ago(10)}"'})
    out = json.loads(_run(tmp_path, "--json").stdout)
    assert out["tracked"] == 1 and out["stale"] == [], json.dumps(out, ensure_ascii=False)


def test_confirm_fixes_duplicate_last_confirmed(tmp_path):
    # 评审 F9:fm 里有重复 last_confirmed 键时,confirm 后不得仍显示过期
    p = tmp_path / "_wiki" / "outputs" / "双键.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\ntitle: 双键\nhalf_life_days: 30\nlast_confirmed: {_days_ago(300)}\n"
                 f"last_confirmed: {_days_ago(300)}\n---\n正文\n", encoding="utf-8")
    assert _run(tmp_path, "--confirm", "_wiki/outputs/双键.md").returncode == 0
    out = json.loads(_run(tmp_path, "--json").stdout)
    assert out["stale"] == [], "confirm 后不得仍过期(重复键未全更新)"


def test_text_output_mentions_urgency(tmp_path):
    _page(tmp_path, "_wiki/outputs/急页.md",
          {"half_life_days": 30, "last_confirmed": _days_ago(90)})   # factor=0.125
    r = _run(tmp_path)
    assert "急页" in r.stdout and ("急" in r.stdout or "⚠" in r.stdout)
