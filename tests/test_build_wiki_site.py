# tests/test_build_wiki_site.py — scripts/build-wiki-site.py 单元测试。
# 文件名带连字符不能直接 import,用 importlib 按路径装载(同 test_build_subscriptions_site.py)。
import importlib.util
import os
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "build_wiki_site",
    Path(__file__).resolve().parent.parent / "scripts" / "build-wiki-site.py")
B = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(B)


def _page(path: Path, title: str, mtime: float):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\ntitle: {title}\n---\n# {title}\n\n一句介绍。\n", encoding="utf-8")
    os.utime(path, (mtime, mtime))


@pytest.fixture()
def mini_vault(tmp_path, monkeypatch):
    """微型 vault:三类页各若干,mtime 可控。"""
    wiki, mat = tmp_path / "_wiki", tmp_path / "material"
    base = 1_700_000_000
    _page(wiki / "concepts" / "旧概念.md", "旧概念", base)
    _page(wiki / "outputs" / "新产出.md", "新产出", base + 300)
    _page(wiki / "outputs" / "中产出.md", "中产出", base + 200)
    _page(mat / "cases" / "新案例.md", "新案例", base + 400)
    _page(mat / "frameworks" / "旧框架.md", "旧框架", base + 100)
    monkeypatch.setattr(B, "WIKI", wiki)
    monkeypatch.setattr(B, "MATERIAL", mat)
    return tmp_path


def test_index_has_recent_section_newest_first(mini_vault):
    """首页必须有「最近更新」区块,按源文件 mtime 降序,新页在前。"""
    pages = B.collect()
    html = B.index_main(B.grouped(pages), pages)
    assert "最近更新" in html, "首页缺「最近更新」区块,新 ingest 的页无处可寻"
    sec = html.split("最近更新", 1)[1]
    order = [sec.find(t) for t in ("新案例", "新产出", "中产出", "旧框架", "旧概念")]
    assert all(i >= 0 for i in order), f"最近更新区块漏页:{order}"
    assert order == sorted(order), f"必须按 mtime 降序(新在前):{order}"


def test_recent_section_links_and_dates(mini_vault):
    """区块里的条目要带链接(可点开)和日期(知道多新)。"""
    import re
    pages = B.collect()
    html = B.index_main(B.grouped(pages), pages)
    sec = html.split("最近更新", 1)[1].split("<h2", 1)[0]
    assert re.search(r'href="[^"]*%E6%96%B0%E6%A1%88%E4%BE%8B[^"]*\.html"', sec), \
        "条目要链到对应页面(quote 后的 slug)"
    assert re.search(r"20\d\d-\d\d-\d\d", sec), "条目要带日期"


def test_recent_section_caps_at_ten(mini_vault):
    """最多 10 条:再多的页也不把首页顶爆。"""
    wiki = mini_vault / "_wiki"
    base = 1_700_001_000
    for i in range(15):
        _page(wiki / "outputs" / f"批量{i:02d}.md", f"批量{i:02d}", base + i)
    pages = B.collect()
    html = B.index_main(B.grouped(pages), pages)
    sec = html.split("最近更新", 1)[1].split("<h2", 1)[0]
    assert sec.count("<li>") <= 10, f"最近更新最多 10 条,实际 {sec.count('<li>')}"
    assert "批量14" in sec and "批量04" not in sec, "留下的必须是最新的那批"
