"""文档站的结构性检查(防链接烂掉、防两份「系统运作」说明分叉)。

「系统运作」有两份载体:`docs/guide/architecture.md`(仓内文字版,ASCII 图)与
`site/architecture.html`(文档站可视化版,手工设计、不由 pandoc 生成)。两份是刻意的
——一份能在 GitHub 上直接读,一份好看——但**刻意的重复必须配一道检查**,否则改了一边
忘另一边就是文档腐烂(CLAUDE.md:想让规范被遵守,就为它写可执行检查)。

顺带把「站内链接不许指向不存在的文件」也钉成门禁:手工页不过 pandoc,没人替你查。
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SITE = REPO / "site"
DOC = REPO / "docs" / "guide" / "architecture.md"
PAGE = SITE / "architecture.html"
TPL = REPO / "scripts" / "site-template.html"

# 七个主题(文字版与可视化版必须都覆盖);取各自措辞里稳定的词根
TOPICS = ["三层架构", "双库", "编译流水线", "四道机器", "查询", "隐私", "Superpowers"]


def test_both_carriers_exist():
    assert DOC.is_file(), "缺文字版:docs/guide/architecture.md"
    assert PAGE.is_file(), "缺可视化版:site/architecture.html"


def test_two_carriers_cover_same_topics():
    md, html = DOC.read_text(encoding="utf-8"), PAGE.read_text(encoding="utf-8")
    for kw in TOPICS:
        assert kw in md, f"文字版缺主题「{kw}」"
        assert kw in html, f"可视化版缺主题「{kw}」"


def test_two_carriers_have_same_section_count():
    """章节数对不上 = 有一边加了/删了内容却没同步。"""
    md = DOC.read_text(encoding="utf-8")
    # 正文章节:## 开头,排除末尾的「相关」链接区
    heads = [h for h in re.findall(r"^## (.+)$", md, re.M) if not h.startswith("相关")]
    sections = re.findall(r'<section class="section">', PAGE.read_text(encoding="utf-8"))
    assert len(heads) == len(sections) == 7, \
        f"文字版 {len(heads)} 节 / 可视化版 {len(sections)} 节,应各 7 节(两边同步改)"


def test_architecture_is_reachable_from_home_and_generated_pages():
    """「放到主页上」不是口头承诺:首页与模板导航都必须链到它。"""
    assert 'href="architecture.html"' in (SITE / "index.html").read_text(encoding="utf-8"), \
        "首页没有链到系统运作页"
    assert 'href="architecture.html"' in TPL.read_text(encoding="utf-8"), \
        "site-template.html 导航缺系统运作,生成页会到不了这一页"


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
