"""更新日志三处载体的同步门禁。

真机事故(2026-08-05):公开版 v1.5 发布出去了,而 https://aip.cab/changelog
还停在 2026-08-03 —— 用户是**打开网页看见的**,不是任何检查报出来的。

拆开看是两处断链,都不在 `build-site.sh` 里(它本身工作正常):

  ① 内容断:发版流程只要求更新 `publish/overrides/CHANGELOG.md`(公开版覆盖),
     私有仓根的 `CHANGELOG.md` 没人管。而**站点渲染的正是后者**
     (`build-site.sh`:`pandoc "$VAULT/CHANGELOG.md" … -o "$SITE/changelog.html"`)。
     两份日志各自独立编号(私有 v1.7 ≈ 公开 v1.3+v1.4),不是同一份文件的两个视图,
     所以"改了一边"不会有任何提示。
  ② 投递断:`site/*.html` 是**提交进仓的生成物**,Cloudflare 从 GitHub main 的
     `site/` 部署。重跑 `build-site.sh` 只是改了工作区 —— 不提交就永远到不了网站。

这两条都是确定性可查的事实,所以做成门禁而不是写进 runbook 让人记
(本仓自己的话:「Prompt 不是检查器」)。pre-push 钩子跑 pytest,
于是**日志没同步就推不出去**,而推不出去就不会有"发布了但网站没更新"。

刻意不做的:不比对 `docs/guide/*.md` 与其 `site/*.html` 的正文是否一致 ——
那要跑 pandoc,且两台机器 pandoc 版本不同会天然产生差异(`MIND_BUILD_SITE`
开关就是为此存在)。这里只查**最新版本号有没有到位**,零依赖、跨机器稳定。
"""
import datetime
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
PRIVATE_CHANGELOG = ROOT / "CHANGELOG.md"
PUBLIC_CHANGELOG = ROOT / "publish" / "overrides" / "CHANGELOG.md"
SITE_CHANGELOG = ROOT / "site" / "changelog.html"

# 公开版树里 `publish/` 整个被 DELETE 清单删掉(公开仓不需要向自己发布),
# 于是"公开版覆盖日志"在那边根本不存在。判据用**目录**而不是文件:
# 目录还在却文件没了,那是私有仓里出了事,必须响亮地失败,不能被当成"在公开树里"而跳过。
IN_PUBLIC_TREE = not (ROOT / "publish").is_dir()
skip_in_public_tree = pytest.mark.skipif(
    IN_PUBLIC_TREE, reason="公开版树没有 publish/overrides/,这条只在私有仓有意义"
)

# `## v1.7 — 2026-08-03`(破折号是 U+2014,与两份日志里实际用的一致)
VERSION_HEADING = re.compile(r"^##\s+(v[\d.]+)\s+—\s+(\d{4}-\d{2}-\d{2})\s*$", re.M)


def _sections(path: pathlib.Path):
    """返回 [(版本号, 日期), …],按文件出现顺序(最新在前)。

    读不到或一条都匹配不到都要**响亮地失败**:静默返回空列表会让下面每条
    断言都变成空集上的真命题,门禁看着全绿实则什么都没查。
    """
    assert path.exists(), f"{path.relative_to(ROOT)} 不存在"
    text = path.read_text(encoding="utf-8")
    found = [
        (m.group(1), datetime.date.fromisoformat(m.group(2)))
        for m in VERSION_HEADING.finditer(text)
    ]
    assert found, (
        f"{path.relative_to(ROOT)} 里一条 `## vX.Y — YYYY-MM-DD` 版本节都没匹配到 —— "
        "要么标题格式变了(破折号是 U+2014 不是 ASCII 减号),要么文件被清空了。"
    )
    return found


@skip_in_public_tree
def test_private_changelog_covers_the_latest_public_release():
    """公开版发布了新版本,私有仓根的 CHANGELOG.md 就必须跟上。

    站点渲染的是私有版;漏写它 = 网站停在旧版,而发布流程一路全绿。
    """
    private_latest_ver, private_latest_date = _sections(PRIVATE_CHANGELOG)[0]
    public_latest_ver, public_latest_date = _sections(PUBLIC_CHANGELOG)[0]
    assert private_latest_date >= public_latest_date, (
        f"公开版已发到 {public_latest_ver}({public_latest_date}),"
        f"而私有仓根 CHANGELOG.md 最新只到 {private_latest_ver}({private_latest_date})。\n"
        "站点 https://aip.cab/changelog 渲染的是**私有版**,不补这一节网站就不会更新。\n"
        "补法:在 CHANGELOG.md 顶部加一节(私有版有自己的编号,不必与公开版对齐,"
        "但写清对应哪个公开版),然后 `bash scripts/build-site.sh` 重建并提交 site/。"
    )


def test_site_changelog_is_not_stale():
    """site/changelog.html 必须已含 CHANGELOG.md 的最新版本节。

    这是「投递断」那一条:改了 Markdown 不重跑 build-site.sh,
    或重跑了不提交 site/,网站都不会变。
    """
    latest_ver, latest_date = _sections(PRIVATE_CHANGELOG)[0]
    assert SITE_CHANGELOG.exists(), "site/changelog.html 不存在 —— 先跑 bash scripts/build-site.sh"
    html = SITE_CHANGELOG.read_text(encoding="utf-8")
    assert latest_ver in html and str(latest_date) in html, (
        f"CHANGELOG.md 最新是 {latest_ver} — {latest_date},"
        "但 site/changelog.html 里找不到它 —— 生成物是旧的。\n"
        "修法:bash scripts/build-site.sh,然后**把 site/ 一起提交**"
        "(Cloudflare 从 GitHub main 的 site/ 部署,不提交等于没发)。"
    )


@pytest.mark.parametrize(
    "path",
    [
        PRIVATE_CHANGELOG,
        pytest.param(PUBLIC_CHANGELOG, marks=skip_in_public_tree),
    ],
)
def test_versions_are_in_descending_date_order(path):
    """版本节按日期倒序(最新在前)—— 上面两条都靠"第一节即最新"这个前提。

    前提写成断言,而不是靠约定:顺序一旦被写乱,上面的门禁会从"查错了"
    退化成"查了个寂寞",而那种失效是无声的。
    """
    dates = [d for _, d in _sections(path)]
    assert dates == sorted(dates, reverse=True), (
        f"{path.relative_to(ROOT)} 的版本节不是按日期倒序:{[str(d) for d in dates]}\n"
        "本文件其余门禁都假定第一节就是最新版,顺序乱了它们会失去意义。"
    )
