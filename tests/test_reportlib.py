"""reportlib 纯函数的 characterization 测试:锁定当前正确行为。
今后改动 reportlib 前,先在这里加一条会失败的测试(RED),再改实现(GREEN)。
运行:python3 -m pytest -q   (pytest.ini 已把 scripts/ 加入 pythonpath)
"""
from datetime import date

import reportlib as R


# ---------- bucket_of:git 路径 → 展示分类(顺序敏感,首个匹配生效) ----------

def test_bucket_of_ingest_and_wiki():
    assert R.bucket_of("raw/clippings/a.md") == "摄入与编译"
    assert R.bucket_of("_wiki/summaries/x.md") == "摄入与编译"
    assert R.bucket_of("_wiki/concepts/y.md") == "摄入与编译"


def test_bucket_of_outputs_not_swallowed_by_ingest():
    # _wiki/outputs 必须归“查询产出”,不能被前一桶的 _wiki/* 抢走
    assert R.bucket_of("_wiki/outputs/查询-x.md") == "查询产出"


def test_bucket_of_material_reports_scripts_docs():
    assert R.bucket_of("material/quotes/a.md") == "写作素材"
    assert R.bucket_of("writing/draft.md") == "写作素材"
    assert R.bucket_of("reports/daily/2026-07-21.md") == "报告"
    assert R.bucket_of("scripts/reportlib.py") == "脚本工具"
    assert R.bucket_of("docs/guide/install.md") == "文档站点"
    assert R.bucket_of("README.md") == "文档站点"
    assert R.bucket_of("CLAUDE.md") == "文档站点"


def test_bucket_of_config_family():
    # 配置桶:config.* 前缀 + .mcp.json / .gitignore / .github/
    assert R.bucket_of("config.glm.yaml") == "配置"
    assert R.bucket_of("config.yaml") == "配置"
    assert R.bucket_of(".mcp.json") == "配置"
    assert R.bucket_of(".github/workflows/x.yml") == "配置"


def test_bucket_of_fallback_and_no_false_prefix():
    assert R.bucket_of("random/other.txt") == "其它"
    # “configuration.md”不应被 config. 前缀误伤(startswith 精确到 config.)
    assert R.bucket_of("configuration.md") == "其它"


# ---------- find_block:标记块定位,前缀容错(短式 begin 命中长式文本) ----------

def test_find_block_prefix_tolerant():
    text = "前言\n<!-- 手记开始 (由你或 LLM 补写) -->\n正文A\n<!-- 手记结束 -->\n尾"
    found = R.find_block(text, R.HAND_BEGIN, R.HAND_END)
    assert found is not None
    _, _, body = found
    assert body == "正文A"


def test_find_block_missing_end_extends_to_eof():
    text = "<!-- 综述开始 -->\n只有开头没有结尾"
    found = R.find_block(text, R.LLM_BEGIN, R.LLM_END)
    assert found is not None
    start, end, body = found
    assert end == len(text)
    assert body == "只有开头没有结尾"


def test_find_block_absent_returns_none():
    assert R.find_block("完全没有标记的文本", R.HAND_BEGIN, R.HAND_END) is None


# ---------- frontmatter / weekday_cn / _sort_key ----------

def test_frontmatter_shape():
    assert R.frontmatter("日报 X", date="2026-07-21") == [
        "---", "title: 日报 X", "type: report", "date: 2026-07-21", "---", "",
    ]


def test_weekday_cn_known_dates():
    # 2026-07-20 是周一(2026-07-11 的周报为 ISO 2026-W28,该周周六即 07-11)
    assert R.weekday_cn("2026-07-20") == "周一"
    assert R.weekday_cn("2026-07-21") == "周二"


def test_sort_key_forms():
    assert R._sort_key("2026-07-21") == "2026-07-21"              # 日报
    assert R._sort_key("2026-07-13_2026-07-19") == "2026-07-13"    # 周报区间
    assert R._sort_key("2026-W28") == "2026-07-06"                # ISO 周 → 周一日期
    assert R._sort_key("乱码") == "乱码"                          # 无法解析原样返回


# ---------- 文件类:preserve_block / extract_hand / atomic_write(用 tmp_path) ----------

def test_preserve_block_keeps_existing(tmp_path):
    p = tmp_path / "r.md"
    p.write_text(f"{R.HAND_BEGIN}\n## 手记\n\n我的真实手记\n{R.HAND_END}\n", encoding="utf-8")
    kept = R.preserve_block(p, R.HAND_BEGIN, R.HAND_END, R.HAND_BODY)
    assert "我的真实手记" in kept
    assert kept.startswith(R.HAND_BEGIN) and kept.endswith(R.HAND_END)


def test_preserve_block_default_when_absent(tmp_path):
    p = tmp_path / "missing.md"
    out = R.preserve_block(p, R.HAND_BEGIN, R.HAND_END, R.HAND_BODY)
    assert out == f"{R.HAND_BEGIN}\n{R.HAND_BODY}\n{R.HAND_END}"


def test_extract_hand_placeholder_is_empty(tmp_path):
    p = tmp_path / "r.md"
    p.write_text(f"{R.HAND_BEGIN}\n{R.HAND_BODY}\n{R.HAND_END}\n", encoding="utf-8")
    assert R.extract_hand(p) == ""   # 未改动的默认留白视为空


def test_extract_hand_returns_real_note(tmp_path):
    p = tmp_path / "r.md"
    p.write_text(f"{R.HAND_BEGIN}\n## 手记\n\n今天完成了拆库\n{R.HAND_END}\n", encoding="utf-8")
    assert R.extract_hand(p) == "今天完成了拆库"


def test_atomic_write_content_and_mode(tmp_path):
    p = tmp_path / "sub" / "out.md"
    R.atomic_write(p, "原子写入内容\n")
    assert p.read_text(encoding="utf-8") == "原子写入内容\n"
    assert oct(p.stat().st_mode)[-3:] == "644"   # 对齐仓库常规 0644
