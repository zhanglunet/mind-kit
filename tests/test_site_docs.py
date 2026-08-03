"""文档站的结构性检查(防链接烂掉、防"一式两份"的说明页分叉)。

站里有若干主题是**刻意做两份载体**的:`docs/guide/<名>.md`(仓内文字版,ASCII 图,
能在 GitHub 上直接读)与 `site/<名>.html`(文档站可视化版,手工设计、不由 pandoc 生成)。
两份都要留——但**刻意的重复必须配一道检查**,否则改了一边忘另一边就是文档腐烂
(CLAUDE.md:想让规范被遵守,就为它写可执行检查)。

顺带把「站内链接不许指向不存在的文件」也钉成门禁:手工页不过 pandoc,没人替你查。
"""
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SITE = REPO / "site"
TPL = REPO / "scripts" / "site-template.html"

# 每对载体:(名字, 章节数, 主题词根)。主题取各自措辞里**稳定**的词根,
# 两份载体都必须覆盖;改文案时别动这些词根,或同步改这里。
PAIRS = [
    ("architecture", 7,
     ["三层架构", "双库", "编译流水线", "四道机器", "查询", "隐私", "Superpowers"]),
    ("okf", 7,
     ["Open Knowledge Format", "取证", "okf.py", "entity_type",
      "流水线", "stale_after", "门禁"]),
]
IDS = [p[0] for p in PAIRS]


def _carriers(name: str):
    return REPO / "docs" / "guide" / f"{name}.md", SITE / f"{name}.html"


@pytest.mark.parametrize("name,_n,_topics", PAIRS, ids=IDS)
def test_both_carriers_exist(name, _n, _topics):
    doc, page = _carriers(name)
    assert doc.is_file(), f"缺文字版:docs/guide/{name}.md"
    assert page.is_file(), f"缺可视化版:site/{name}.html"


@pytest.mark.parametrize("name,_n,topics", PAIRS, ids=IDS)
def test_two_carriers_cover_same_topics(name, _n, topics):
    doc, page = _carriers(name)
    md, html = doc.read_text(encoding="utf-8"), page.read_text(encoding="utf-8")
    for kw in topics:
        assert kw in md, f"{name} 文字版缺主题「{kw}」"
        assert kw in html, f"{name} 可视化版缺主题「{kw}」"


@pytest.mark.parametrize("name,count,_topics", PAIRS, ids=IDS)
def test_two_carriers_have_same_section_count(name, count, _topics):
    """章节数对不上 = 有一边加了/删了内容却没同步。"""
    doc, page = _carriers(name)
    md = doc.read_text(encoding="utf-8")
    # 正文章节:## 开头,排除末尾的「相关」链接区
    heads = [h for h in re.findall(r"^## (.+)$", md, re.M) if not h.startswith("相关")]
    sections = re.findall(r'<section class="section">', page.read_text(encoding="utf-8"))
    assert len(heads) == len(sections) == count, \
        f"{name}:文字版 {len(heads)} 节 / 可视化版 {len(sections)} 节,应各 {count} 节(两边同步改)"


@pytest.mark.parametrize("name,_n,_topics", PAIRS, ids=IDS)
def test_manual_pages_are_reachable_from_home_and_generated_pages(name, _n, _topics):
    """「放到站上」不是口头承诺:首页与模板导航都必须链到它。

    手工页不进 build-site.sh 的构建清单,没有任何机制会自动把它挂上导航——
    漏挂就是一个只有知道 URL 才进得去的孤儿页。
    """
    href = f'href="{name}.html"'
    assert href in (SITE / "index.html").read_text(encoding="utf-8"), \
        f"首页没有链到 {name}.html"
    assert href in TPL.read_text(encoding="utf-8"), \
        f"site-template.html 导航缺 {name}.html,生成页会到不了这一页"


def _internal_targets(html: str):
    """页面里指向站内文件的链接/资源(排除外链、锚点、mailto)。"""
    out = []
    for attr in ("href", "src"):
        for v in re.findall(rf'{attr}="([^"]+)"', html):
            if v.startswith(("http://", "https://", "#", "mailto:", "data:")):
                continue
            out.append(v.split("#")[0].split("?")[0])
    return [v for v in out if v]


def test_no_broken_internal_links():
    broken = []
    for p in sorted(SITE.rglob("*.html")):
        for target in _internal_targets(p.read_text(encoding="utf-8")):
            base = SITE if target.startswith("/") else p.parent
            dest = base / target.lstrip("/")
            if target.endswith("/") or target in ("", "/"):
                dest = dest / "index.html"
            if not dest.exists():
                broken.append(f"{p.relative_to(REPO)} → {target}")
    assert not broken, "站内死链:\n" + "\n".join(broken)
