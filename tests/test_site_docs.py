"""文档站的结构性检查(防链接烂掉、防"一式两份"的说明页分叉)。

站里有若干主题是**刻意做两份载体**的:`docs/guide/<名>.md`(仓内文字版,ASCII 图,
能在 GitHub 上直接读)与 `site/<名>.html`(文档站可视化版,手工设计、不由 pandoc 生成)。
两份都要留——但**刻意的重复必须配一道检查**,否则改了一边忘另一边就是文档腐烂
(CLAUDE.md:想让规范被遵守,就为它写可执行检查)。

顺带把「站内链接不许指向不存在的文件」也钉成门禁:手工页不过 pandoc,没人替你查。
"""
import re
import zipfile
from html import unescape
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SITE = REPO / "site"
TPL = REPO / "scripts" / "site-template.html"

# 每对载体:(名字, 章节数, 主题词根)。主题取各自措辞里**稳定**的词根,
# 两份载体都必须覆盖;改文案时别动这些词根,或同步改这里。
PAIRS = [
    ("architecture", 9,
     ["四层一图", "三层架构", "双库", "编译流水线", "四道机器", "查询", "隐私",
      "Superpowers", "运行时"]),
    ("okf", 8,
     ["Open Knowledge Format", "取证", "okf.py", "entity_type",
      "流水线", "stale_after", "门禁", "四层"]),
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


def test_logo_download_assets_are_published():
    page = SITE / "logo.html"
    assets = SITE / "assets" / "downloads"
    expected = {
        "second-brain-logo.svg", "second-brain-logo.png", "second-brain-logo.jpg",
        "second-brain-app-icon.svg", "second-brain-app-icon.png", "second-brain-app-icon.jpg",
    }
    assert expected.issubset({p.name for p in assets.iterdir()})
    html = page.read_text(encoding="utf-8")
    for name in expected:
        assert f'assets/downloads/{name}' in html, f"logo.html 缺少下载链接: {name}"


def test_workbuddy_downloadable_skill_package_is_published():
    package = SITE / "downloads" / "workbuddy-second-brain-skill-v1.0.1.zip"
    page = SITE / "workbuddy.html"
    assert package.is_file(), "WorkBuddy 安装包未发布到 site/downloads"
    page_text = page.read_text(encoding="utf-8")
    assert "downloads/workbuddy-second-brain-skill-v1.0.1.zip" in page_text
    assert "第二大脑 WorkBuddy 技能包" in re.sub(r"\s+", " ", page_text)
    assert "官方“专家”或技能市场" in page_text
    assert "https://skillhub.cn/skills/user_4c0191ff/mind" in page_text
    with zipfile.ZipFile(package) as archive:
        names = set(archive.namelist())
        assert {"README.md", "SKILL.md", "skill.yaml"}.issubset(names)
        assert "expert.yaml" not in names
        skill = archive.read("SKILL.md").decode("utf-8")
        assert skill.startswith("---\n")
        assert "App Secret" in skill
        assert "access token" in skill
        assert "sk-" not in skill


def test_workbuddy_guide_is_built_and_reachable():
    source = REPO / "docs" / "guide" / "workbuddy.md"
    page = SITE / "workbuddy.html"
    assert source.is_file(), "缺 Workbuddy 指导页 Markdown 真源"
    assert page.is_file(), "缺构建产物 site/workbuddy.html"
    md = source.read_text(encoding="utf-8")
    rendered = page.read_text(encoding="utf-8")
    rendered_flat = re.sub(r"\s+", " ", rendered)
    for required in (
        "https://github.com/zhanglunet/mind-kit.git", "./install-second-brain", "提示词 1", "提示词 2",
        "App Secret", "127.0.0.1", "授权完成并开始同步", "missing_scope",
        "Windows 10/11", "PowerShell", "不需要 WSL2", "install-second-brain.ps1",
        "compile-second-brain.ps1", "bash scripts/compile.sh",
        "usage.html", "http://127.0.0.1:8788/browse/index.html",
    ):
        assert required in md, f"Workbuddy 指南缺关键内容:{required}"
        rendered_required = required.replace("<", "&lt;").replace(">", "&gt;")
        assert rendered_required in rendered_flat or required in rendered_flat
    href = 'href="workbuddy.html"'
    assert href in (SITE / "index.html").read_text(encoding="utf-8"), "首页没入口"
    assert href in TPL.read_text(encoding="utf-8"), "生成页导航没入口"
    assert '&lt;a class=&quot;wb-primary&quot;' not in rendered, "页首 CTA 被 pandoc 误渲染成代码"


def test_codex_guide_is_built_and_reachable():
    source = REPO / "docs" / "guide" / "codex.md"
    page = SITE / "codex.html"
    assert source.is_file(), "缺 Codex 指导页 Markdown 真源"
    assert page.is_file(), "缺构建产物 site/codex.html"
    md = source.read_text(encoding="utf-8")
    rendered_html = page.read_text(encoding="utf-8")
    rendered = re.sub(r"\s+", " ", rendered_html)
    rendered_text = re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", rendered_html)))
    for required in (
        "Codex", "mind-kit", "install-second-brain", "127.0.0.1",
        "App Secret", "missing_scope", "同步完成", "compile-second-brain.ps1",
        "不使用 WSL", "飞书开发者后台",
    ):
        assert required in md, f"Codex 指南缺关键内容:{required}"
        assert required.replace("<", "&lt;").replace(">", "&gt;") in rendered or required in rendered or required in rendered_text
    assert 'href="codex.html"' in (SITE / "index.html").read_text(encoding="utf-8")
    assert 'href="codex.html"' in TPL.read_text(encoding="utf-8")
    assert 'href="codex.html"' in (SITE / "sitemap.html").read_text(encoding="utf-8")
    assert "https://aip.cab/codex" in (SITE / "sitemap.xml").read_text(encoding="utf-8")


def test_sitemap_page_and_search_index_exist():
    sitemap = SITE / "sitemap.html"
    xml = SITE / "sitemap.xml"
    robots = SITE / "robots.txt"
    assert sitemap.is_file(), "缺可见站点地图"
    assert xml.is_file(), "缺搜索引擎 sitemap.xml"
    assert robots.is_file(), "缺 robots.txt"
    page = sitemap.read_text(encoding="utf-8")
    assert 'href="sitemap.html"' in page
    assert "https://aip.cab/sitemap.xml" in robots.read_text(encoding="utf-8")
    xml_text = xml.read_text(encoding="utf-8")
    for path in ("https://aip.cab/", "https://aip.cab/workbuddy", "https://aip.cab/sitemap"):
        assert f"<loc>{path}</loc>" in xml_text
    assert 'href="sitemap.html"' in (SITE / "index.html").read_text(encoding="utf-8")
    assert 'href="sitemap.html"' in TPL.read_text(encoding="utf-8")


def test_primary_navigation_stays_focused():
    """主导航只保留最常用入口；长尾文档留在首页卡片和页脚。"""
    expected = {
        "workbuddy.html": "开始安装",
        "architecture.html": "系统原理",
        "compare.html": "产品比较",
        "usage.html": "使用指南",
        "services.html": "获取与服务",
        "https://github.com/zhanglunet/mind-kit": "GitHub",
    }
    pages = [SITE / "index.html", SITE / "architecture.html", SITE / "okf.html", TPL]
    for page in pages:
        html = page.read_text(encoding="utf-8")
        nav = re.search(r'<div class="navlinks">(.*?)</div>', html, re.S)
        assert nav, f"{page.name} 缺主导航"
        primary = nav.group(1).split('<details class="nav-more">', 1)[0]
        links = re.findall(r'<a href="([^"]+)"[^>]*>([^<]+)</a>', primary)
        assert len(links) == 6, f"{page.name} 主导航应为 6 项，实际 {len(links)} 项"
        assert dict(links) == expected, f"{page.name} 主导航与统一信息架构不一致"


def test_no_mojibake_in_site_pages():
    """烧进 HTML 的 U+FFFD = 构建机器 locale 是 C,argv 里的中文按单字节解码报废。

    真机实测:changelog/prd 两页的标题经 `--metadata title=...` 传入,在 C locale
    的 VM 上构建后 title 与面包屑全是「�」。build-site.sh 已改走 --metadata-file
    (pandoc 恒按 UTF-8 读),这道门禁防止任何路径把乱码重新带进来。
    """
    bad = []
    for p in sorted(SITE.rglob("*.html")):
        if "�" in p.read_text(encoding="utf-8"):
            bad.append(str(p.relative_to(REPO)))
    assert not bad, "页面含 U+FFFD 乱码(用 UTF-8 locale 重建 site/):\n" + "\n".join(bad)


def test_svg_text_has_no_literal_markdown():
    """SVG 的 `<text>` **不渲染 markdown** —— 写 `**粗体**` 会把星号原样显示出来。

    2026-08-04 实测栽过:运行时信息图里五处 `**…**` 全部漏成了字面星号。
    写 SVG 时手感和写 markdown 一样,很容易顺手带上;而它只在渲染出来的图上
    才看得见,读代码看不出来 —— 正好是门禁该管的那类。

    要强调就用 class(如 sg-gate / sg-lab),不要用 markdown 记号。
    """
    bad = []
    for p in sorted(SITE.glob("*.html")):
        for m in re.finditer(r"<text[^>]*>([^<]*)</text>", p.read_text(encoding="utf-8")):
            t = m.group(1)
            if "**" in t or "`" in t:
                bad.append(f"{p.name}: {t.strip()[:60]}")
    assert not bad, "SVG <text> 里混进了 markdown 记号(不会被渲染,只会漏成字面量):\n  " + "\n  ".join(bad)


# ── 生成页也不许成为孤儿页 ────────────────────────────────────────────────
# 既有的 `test_manual_pages_are_reachable_from_home_and_generated_pages` 只覆盖
# **手工页**(architecture / okf)。而 `build-site.sh` 里 `build_page` 生成的页
# **没有任何机制**保证它被挂上导航 —— 加了一行 build_page 却忘了改模板,
# 结果是一个"只有知道 URL 才进得去"的页面,而且**构建不会有任何抱怨**。
#
# 这道检查从 build-site.sh **自己**读清单,不维护第二份名单:
# 名单一旦要人手同步,它迟早和真相分叉(本仓一贯的判断)。

BUILD_SH = REPO / "scripts" / "build-site.sh"


def _generated_pages():
    """从 build-site.sh 的 `build_page <md> <out.html> <active>` 行里读出生成页。"""
    src = BUILD_SH.read_text(encoding="utf-8")
    rows = re.findall(r'^build_page\s+\S+\s+(\S+\.html)\s+(\S+)\s*$', src, re.M)
    assert rows, "从 build-site.sh 里一个 build_page 行都没读出来 —— 正则或脚本变了"
    return rows


def test_every_generated_page_is_on_the_nav():
    tpl = TPL.read_text(encoding="utf-8")
    missing = [out for out, _ in _generated_pages() if f'href="{out}"' not in tpl]
    assert not missing, (
        "这些页由 build-site.sh 生成,却没挂在 site-template.html 的导航里,"
        "会成为只有知道 URL 才进得去的孤儿页:\n  " + "\n  ".join(missing))


def test_every_generated_page_has_its_active_marker():
    """导航高亮变量对不上 = 页面在导航里不会被标为当前页(低级但很显眼的坏体验)。"""
    tpl = TPL.read_text(encoding="utf-8")
    missing = [f"{out} → active_{act}" for out, act in _generated_pages()
               if f"active_{act}" not in tpl]
    assert not missing, "导航模板缺这些高亮变量:\n  " + "\n  ".join(missing)


def test_every_generated_page_is_linked_from_the_home_page():
    """首页是唯一入口页,生成页也必须能从它到达。"""
    home = (SITE / "index.html").read_text(encoding="utf-8")
    missing = [out for out, _ in _generated_pages() if f'href="{out}"' not in home]
    assert not missing, "首页没有链到这些生成页:\n  " + "\n  ".join(missing)
