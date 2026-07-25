"""validate_write_set.py 写集校验的行为测试(P1-4)。
契约:
- 输入 --path ×N / --paths-file / --git-changed;空写集 exit 2(拒绝假绿)。
- 逐页确定性检查(只校验给定页,不扫全库):UTF-8、fm 闭合与键值形态、重复键、
  含「: 」的值必须引号化(URL 无冒号空格不误伤)、保鲜字段合法(含未来日期)、
  decisions/ 记录不变量、宿主临时路径引用(uploads / /tmp/claude-)。
- 引擎领地(_wiki/{summaries,concepts,entities})显式给到也跳过(报 skipped);log.md 只查 UTF-8。
- 全过 exit 0;有错 exit 1。
"""
import json
import subprocess
from datetime import date, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CLI = REPO / "scripts" / "validate_write_set.py"


def _run(vault: Path, *args):
    return subprocess.run(["python3", str(CLI), "--vault", str(vault), *args],
                          capture_output=True, text=True, cwd=str(REPO))


def _page(vault: Path, rel: str, text: str) -> Path:
    p = vault / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


GOOD = "---\ntitle: 好页面\nvolatility: low\nlast_confirmed: 2026-07-01\n---\n\n正文。\n"


def test_empty_write_set_is_usage_error(tmp_path):
    r = _run(tmp_path)
    assert r.returncode == 2


def test_clean_page_passes(tmp_path):
    _page(tmp_path, "_wiki/outputs/好页.md", GOOD)
    r = _run(tmp_path, "--path", "_wiki/outputs/好页.md", "--json")
    assert r.returncode == 0, r.stdout + r.stderr
    out = json.loads(r.stdout)
    assert out["failed"] == 0 and out["checked"] == 1


def test_unclosed_frontmatter_fails(tmp_path):
    _page(tmp_path, "_wiki/outputs/断栏.md", "---\ntitle: 断栏\n\n正文没有闭合栏。\n")
    assert _run(tmp_path, "--path", "_wiki/outputs/断栏.md").returncode == 1


def test_duplicate_fm_keys_fail(tmp_path):
    _page(tmp_path, "_wiki/outputs/双键.md",
          "---\ntitle: 双键\ntitle: 又一个\n---\n正文\n")
    r = _run(tmp_path, "--path", "_wiki/outputs/双键.md", "--json")
    assert r.returncode == 1
    assert "重复" in json.dumps(json.loads(r.stdout)["results"], ensure_ascii=False)


def test_unquoted_colon_value_fails_url_ok(tmp_path):
    # P1-2 评审的"看板隐身"病:值含「: 」必须引号;URL(无冒号空格)不得误伤
    _page(tmp_path, "_wiki/outputs/冒号值.md",
          "---\ntitle: P1-4: 写集校验\n---\n正文\n")
    assert _run(tmp_path, "--path", "_wiki/outputs/冒号值.md").returncode == 1
    _page(tmp_path, "_wiki/outputs/带链接.md",
          '---\ntitle: "P1-4: 写集校验"\nsource: https://example.com/a\n---\n正文\n')
    r = _run(tmp_path, "--path", "_wiki/outputs/带链接.md")
    assert r.returncode == 0, "引号化标题与 URL 值都应通过:" + r.stdout + r.stderr


def test_bad_freshness_fields_fail(tmp_path):
    _page(tmp_path, "material/frameworks/坏保鲜.md",
          "---\nhalf_life_days: oops\n---\n正文\n")
    assert _run(tmp_path, "--path", "material/frameworks/坏保鲜.md").returncode == 1
    future = (date.today() + timedelta(days=999)).isoformat()
    _page(tmp_path, "material/frameworks/未来页.md",
          f"---\nvolatility: low\nlast_confirmed: {future}\n---\n正文\n")
    assert _run(tmp_path, "--path", "material/frameworks/未来页.md").returncode == 1


def test_host_temp_path_reference_fails(tmp_path):
    # FR-ING-08 证据链:产出不得引用宿主临时上传路径
    _page(tmp_path, "_wiki/outputs/引临时路径.md",
          "---\ntitle: x\n---\n附件见 /root/.claude/uploads/abc/file.zip。\n")
    r = _run(tmp_path, "--path", "_wiki/outputs/引临时路径.md", "--json")
    assert r.returncode == 1
    assert "临时" in json.dumps(json.loads(r.stdout)["results"], ensure_ascii=False)


def test_decision_record_invariants_checked(tmp_path):
    _page(tmp_path, "_wiki/outputs/decisions/DEC-20260723-01-坏.md",
          "---\ntitle: 坏记录\ndecision_id: DEC-20260723-01\ndecision_type: promote\n"
          "decision_status: approved\ncreated: 2026-07-23\n---\n正文\n")   # approved 缺 decided_at
    assert _run(tmp_path, "--path", "_wiki/outputs/decisions/DEC-20260723-01-坏.md").returncode == 1
    _page(tmp_path, "_wiki/outputs/decisions/DEC-20260723-02-好.md",
          "---\ntitle: 好记录\ndecision_id: DEC-20260723-02\ndecision_type: promote\n"
          "decision_status: pending\ncreated: 2026-07-23\n---\n正文\n")
    assert _run(tmp_path, "--path", "_wiki/outputs/decisions/DEC-20260723-02-好.md").returncode == 0


def test_engine_territory_skipped(tmp_path):
    # 引擎领地页显式给到也不校(engine 输出我们修不了,归 lint);skipped 不算失败
    _page(tmp_path, "_wiki/concepts/概念.md", "---\ntitle: A: B\n---\n")   # 若被校会红
    r = _run(tmp_path, "--path", "_wiki/concepts/概念.md", "--json")
    assert r.returncode == 0
    assert json.loads(r.stdout)["skipped"] == 1


def test_non_utf8_fails(tmp_path):
    p = tmp_path / "_wiki" / "outputs" / "坏编码.md"
    p.parent.mkdir(parents=True)
    p.write_bytes("---\ntitle: x\n---\n中文".encode("gbk"))
    assert _run(tmp_path, "--path", "_wiki/outputs/坏编码.md").returncode == 1


def test_raw_and_docs_out_of_scope_skipped(tmp_path):
    # 评审 F1 HIGH:校验面必须是 LLM 领地白名单——raw/ 剪藏(标题带冒号、非 UTF-8)
    # 不得拦提交(宪法禁改 raw 原件,拦了连修复路径都没有);docs/ 同理出圈
    _page(tmp_path, "raw/clippings/网文.md",
          "---\ntitle: How to X: A Complete Guide\n---\n剪藏正文\n")
    p = tmp_path / "raw" / "flomo" / "2026-07" / "导出.md"
    p.parent.mkdir(parents=True)
    p.write_bytes("非 UTF-8 内容".encode("gbk"))
    _page(tmp_path, "docs/dev-log.md", "描述 /tmp/claude- 路径的文档行\n")
    r = _run(tmp_path, "--path", "raw/clippings/网文.md",
             "--path", "raw/flomo/2026-07/导出.md", "--path", "docs/dev-log.md", "--json")
    assert r.returncode == 0, "领地外文件必须跳过:" + r.stdout + r.stderr
    assert json.loads(r.stdout)["skipped"] == 3


def test_block_list_and_single_quote_pass(tmp_path):
    # 评审 F2:块式列表(Obsidian 属性面板默认写法)与单引号标量是合法 YAML,不得误拦
    _page(tmp_path, "_wiki/outputs/五维页.md",
          "---\ntitle: '带冒号: 的单引号标题'\ndimension:\n  - 市场与竞争\n  - 技术判断\n"
          "tags:\n- 顶格列表项\n# 注释行\n---\n正文\n")
    r = _run(tmp_path, "--path", "_wiki/outputs/五维页.md", "--json")
    assert r.returncode == 0, r.stdout + r.stderr


def test_empty_frontmatter_ok(tmp_path):
    # 评审 F9:空 fm(Obsidian 清空属性后残留)不得误报"未闭合"
    _page(tmp_path, "_wiki/outputs/空fm.md", "---\n---\n正文\n")
    assert _run(tmp_path, "--path", "_wiki/outputs/空fm.md").returncode == 0


def test_decisions_readme_not_treated_as_record(tmp_path):
    # 评审 F5:decisions/ 下 README 等辅助文件不套记录不变量;只有 DEC-*.md 才校
    _page(tmp_path, "_wiki/outputs/decisions/README.md",
          "---\ntitle: 目录说明\n---\n说明文字\n")
    r = _run(tmp_path, "--path", "_wiki/outputs/decisions/README.md", "--json")
    assert r.returncode == 0, r.stdout + r.stderr


def test_chinese_key_ascii_colon_passes(tmp_path):
    # 本机演练误伤(2026-07-23):中文键名 + ASCII 冒号是合法 YAML / 合法 Obsidian 属性,
    # 不得误拦——旧 KEY_RE 限键名首字符 [A-Za-z_] 会把存量中文 fm 键全部误判
    _page(tmp_path, "_wiki/outputs/中文键页.md",
          "---\n类别: ingest 摘要\n主体: 某人的个人说明书 v2.0\n"
          "来源: 飞书云文档(feishu-docx)\nvolatility: low\n---\n正文\n")
    r = _run(tmp_path, "--path", "_wiki/outputs/中文键页.md", "--json")
    assert r.returncode == 0, "中文键名合法,不该拦:" + r.stdout + r.stderr
    assert json.loads(r.stdout)["failed"] == 0


def test_fullwidth_colon_still_caught_as_malformed(tmp_path):
    # 全角冒号「:」当分隔符仍是坏页(YAML 只认 ASCII 冒号):不必特殊消息,
    # 朴素 KEY_RE 不匹配即落到"非 key: value"被拦,安全性不靠专用分支
    _page(tmp_path, "material/frameworks/坏分隔符.md",
          "---\n类别：框架\n---\n正文\n")
    assert _run(tmp_path, "--path", "material/frameworks/坏分隔符.md").returncode == 1


def test_porcelain_parse_rename_and_copy_entries():
    # 评审 F7:R/C 条目都带旧路径需跳过;删除不校;非 .md 过滤
    import importlib.util
    spec = importlib.util.spec_from_file_location("vws", CLI)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    stdout = "R  新 页.md\0旧 页.md\0?? 新增.md\0C  拷贝.md\0来源.md\0 D 删掉.md\0M  改动.txt\0M  好.md\0"
    got = m._parse_porcelain_z(stdout)
    assert got == ["新 页.md", "新增.md", "拷贝.md", "好.md"], got


def test_git_changed_mode_picks_up_modified_md(tmp_path):
    subprocess.run(["git", "-C", str(tmp_path), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "t"], check=True)
    _page(tmp_path, "_wiki/outputs/已入库.md", GOOD)
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "init"], check=True)
    # 一个新增坏页 + 一个未动好页:--git-changed 只该看见坏页 → 整体红
    _page(tmp_path, "_wiki/outputs/新坏页.md", "---\ntitle: 断栏\n\n没闭合\n")
    r = _run(tmp_path, "--git-changed", "--json")
    assert r.returncode == 1
    out = json.loads(r.stdout)
    assert out["checked"] == 1, f"应只校验变更的 1 页:{out}"
