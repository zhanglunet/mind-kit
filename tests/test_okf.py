"""okf.py —— Open Knowledge Format v0.2 合规注入与检查。

契约(OKF 硬性要求只有三条,这里只管前两条;index.md/log.md 归 §8-9 另议):
1. 每个非保留 `.md` 有合法 YAML frontmatter
2. 每个 frontmatter 的 `type` 非空

设计要点:
- **确定性映射,不用 LLM**:type 的值从目录 + 已有键(entity_type / source_type)推出。
- **幂等**:已有 OKF 键就一个字节都不写。引擎领地的页每轮编译都会被后处理扫一遍,
  不幂等的话每轮都改动文件 → 触发 sage-wiki 的 reconcile churn、git 每天一堆空 diff。
- **保留原键**:`entity_type` / `类别` / `decision_type` 原样留着。OKF 明确要求消费者
  容忍未知键,而这些键有现成消费者(build-index.py / build-wiki-site.py / Obsidian 属性面板),
  改名等于砸自家管线。
- **只加不改**:已有 `type` 的页(reports 全部、outputs 十来页)一律不碰。
"""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CLI = REPO / "scripts" / "okf.py"


def _run(vault: Path, *args):
    return subprocess.run([sys.executable, str(CLI), "--vault", str(vault), *args],
                          capture_output=True, text=True, cwd=str(REPO))


def _page(vault: Path, rel: str, text: str) -> Path:
    p = vault / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def _fm(p: Path) -> dict:
    """极简 frontmatter 解析,只为断言用。"""
    lines = p.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    out = {}
    for ln in lines[1:]:
        if ln.strip() == "---":
            break
        if ":" in ln:
            k, _, v = ln.partition(":")
            out[k.strip()] = v.strip()
    return out


# ---------- type 注入 ----------

def test_concept_type_comes_from_entity_type(tmp_path):
    """概念页:值直接取自已有的 entity_type,不是硬编码。

    真实页长这样(取证自 mind-vault):
        concept: AI-native国家战略
        entity_type: concept
    OKF 要的 type 语义上就是它,所以搬过来即可 —— 而且 entity_type 有两个现成消费者
    (build-index.py:71、build-wiki-site.py:107),**必须原样保留**。
    """
    _page(tmp_path, "_wiki/concepts/某技术.md",
          "---\nconcept: 某技术\nentity_type: technique\naliases: []\n---\n正文\n")
    r = _run(tmp_path, "--fix")
    assert r.returncode == 0, r.stdout + r.stderr
    fm = _fm(tmp_path / "_wiki/concepts/某技术.md")
    assert fm["type"] == "technique", f"type 应取自 entity_type:{fm}"
    assert fm["entity_type"] == "technique", "entity_type 必须原样保留(有现成消费者)"


def test_concept_without_entity_type_falls_back(tmp_path):
    _page(tmp_path, "_wiki/concepts/无类型.md", "---\nconcept: 无类型\n---\n正文\n")
    _run(tmp_path, "--fix")
    assert _fm(tmp_path / "_wiki/concepts/无类型.md")["type"] == "concept"


def test_summary_and_decision_and_material_types(tmp_path):
    _page(tmp_path, "_wiki/summaries/raw-clippings-x.md",
          "---\nsource: raw/clippings/x.md\nsource_type: article\n---\n摘要\n")
    _page(tmp_path, "_wiki/outputs/decisions/DEC-20260724-01-试.md",
          "---\ntitle: 试\ndecision_id: DEC-20260724-01\ndecision_type: promote\n---\n正文\n")
    _page(tmp_path, "material/quotes/句子.md", "---\n类别: ① 原创金句\n---\n正文\n")
    _run(tmp_path, "--fix")
    assert _fm(tmp_path / "_wiki/summaries/raw-clippings-x.md")["type"] == "summary"
    assert _fm(tmp_path / "_wiki/outputs/decisions/DEC-20260724-01-试.md")["type"] == "decision"
    m = _fm(tmp_path / "material/quotes/句子.md")
    assert m["type"] == "material"
    assert "类别" in m, "中文键必须原样保留(Obsidian 属性面板 + build-wiki-site 在读)"


def test_existing_type_is_never_touched(tmp_path):
    """已有 type 的页一律不碰 —— reports 全部、outputs 十来页都已经有了。"""
    before = "---\ntitle: 日报 2026-07-14\ntype: report\ndate: 2026-07-14\n---\n正文\n"
    p = _page(tmp_path, "reports/daily/2026-07-14.md", before)
    _run(tmp_path, "--fix")
    assert p.read_text(encoding="utf-8") == before, "已有 type 的页不许改动一个字节"


def test_reserved_files_and_writing_are_skipped(tmp_path):
    """index.md / log.md 是 OKF 保留文件(不得有 frontmatter);writing/ 不属于 bundle。"""
    idx = _page(tmp_path, "_wiki/index.md", "# 内容导航 Index\n\n- [[某页]]\n")
    log = _page(tmp_path, "_wiki/log.md", "# 时序日志 Log\n\n## [2026-07-14] ingest ｜ x\n")
    w = _page(tmp_path, "writing/稿子.md", "随手写的稿子,没有 frontmatter\n")
    _run(tmp_path, "--fix")
    for p in (idx, log, w):
        assert "type:" not in p.read_text(encoding="utf-8"), f"{p.name} 不该被注入"


def test_fix_is_idempotent(tmp_path):
    """跑第二遍必须**一个字节都不改**。

    引擎领地的页每轮编译都会被扫,不幂等的话:每轮都产生 git 改动、
    每轮都触发 sage-wiki 的 reconcile —— 日志噪音 + 无意义提交。
    """
    _page(tmp_path, "_wiki/concepts/甲.md", "---\nconcept: 甲\nentity_type: claim\n---\n正文\n")
    _run(tmp_path, "--fix")
    once = (tmp_path / "_wiki/concepts/甲.md").read_bytes()
    r2 = _run(tmp_path, "--fix")
    assert (tmp_path / "_wiki/concepts/甲.md").read_bytes() == once, "第二遍不该改动文件"
    assert "0 " in r2.stdout or "无需" in r2.stdout, f"第二遍应报告 0 改动:{r2.stdout}"


def test_page_without_frontmatter_gets_one(tmp_path):
    """OKF 条件 1:非保留 .md 必须**有** frontmatter。缺就补。"""
    _page(tmp_path, "material/cases/裸页.md", "# 标题\n\n正文没有 frontmatter。\n")
    _run(tmp_path, "--fix")
    txt = (tmp_path / "material/cases/裸页.md").read_text(encoding="utf-8")
    assert txt.startswith("---\n"), "应补出 frontmatter"
    assert _fm(tmp_path / "material/cases/裸页.md")["type"] == "material"
    assert "# 标题" in txt and "正文没有 frontmatter。" in txt, "正文必须原样保留"


# ---------- stale_after(档二的那一件) ----------

def test_stale_after_computed_from_freshness_fields(tmp_path):
    """`stale_after` = last_confirmed + 半衰期。算式 freshness.py 已经有,这里只是写回。

    只对**已声明保鲜**的页生效(有 volatility 或 half_life_days);没声明的不碰 ——
    与 freshness.py 的既有语义一致:不加字段就不参与追踪。
    """
    _page(tmp_path, "_wiki/outputs/易变页.md",
          "---\ntitle: 易变页\ntype: output\nvolatility: high\nlast_confirmed: 2026-01-01\n---\n正文\n")
    _page(tmp_path, "_wiki/outputs/不追踪.md", "---\ntitle: 不追踪\ntype: output\n---\n正文\n")
    r = _run(tmp_path, "--fix")
    assert r.returncode == 0, r.stdout + r.stderr
    # high → 半衰期 30 天 → 2026-01-01 + 30 = 2026-01-31
    assert _fm(tmp_path / "_wiki/outputs/易变页.md")["stale_after"] == "2026-01-31"
    assert "stale_after" not in _fm(tmp_path / "_wiki/outputs/不追踪.md"), \
        "没声明保鲜的页不该被塞 stale_after"


def test_explicit_half_life_wins(tmp_path):
    _page(tmp_path, "_wiki/outputs/显式.md",
          "---\ntype: output\nvolatility: low\nhalf_life_days: 10\nlast_confirmed: 2026-03-01\n---\n正文\n")
    _run(tmp_path, "--fix")
    assert _fm(tmp_path / "_wiki/outputs/显式.md")["stale_after"] == "2026-03-11"


# ---------- check 模式 ----------

def test_check_reports_and_exits_nonzero_when_nonconformant(tmp_path):
    """`--check` 是只读的合规体检,发现不合规必须**非零退出**。

    引擎领地此前是**零门禁**(validate_write_set.py 的 LLM_SCOPE 不含
    _wiki/{summaries,concepts,entities}),引擎写出什么都没人看。这条补上。
    """
    _page(tmp_path, "_wiki/concepts/缺type.md", "---\nconcept: x\n---\n正文\n")
    r = _run(tmp_path, "--check")
    assert r.returncode != 0, "有不合规页必须非零退出"
    assert "缺type" in r.stdout or "缺 type" in r.stdout, r.stdout


def test_check_is_read_only(tmp_path):
    p = _page(tmp_path, "_wiki/concepts/缺type.md", "---\nconcept: x\n---\n正文\n")
    before = p.read_bytes()
    _run(tmp_path, "--check")
    assert p.read_bytes() == before, "--check 不得写文件"


def test_check_clean_after_fix(tmp_path):
    _page(tmp_path, "_wiki/concepts/甲.md", "---\nconcept: 甲\nentity_type: concept\n---\n正文\n")
    _page(tmp_path, "material/quotes/乙.md", "---\n类别: ① 原创金句\n---\n正文\n")
    _run(tmp_path, "--fix")
    r = _run(tmp_path, "--check")
    assert r.returncode == 0, "fix 之后 check 必须干净:" + r.stdout + r.stderr


def test_auxiliary_files_get_meaningful_types(tmp_path):
    """OKF 只保留 index.md / log.md 两个文件名;CHANGELOG/README 同样要有 type。

    真实库里 `_wiki/CHANGELOG.md` 就是这么一页 —— 不给它一个像样的 type,
    它会落到兜底的 `note`,语义上没意义。
    """
    _page(tmp_path, "_wiki/CHANGELOG.md", "# 变更\n\n- 略\n")
    _page(tmp_path, "material/README.md", "# 说明\n")
    _run(tmp_path, "--fix")
    assert _fm(tmp_path / "_wiki/CHANGELOG.md")["type"] == "changelog"
    assert _fm(tmp_path / "material/README.md")["type"] == "readme"


def test_compile_pipeline_wires_okf_in_the_right_order():
    """`--fix` 在重建 index 之前,`--check` 在 lint 记账里。

    **2026-08-04 更正**:本条原来的理由写错了 —— 说的是"否则索引读到旧 frontmatter"。
    实测 `build-index.py` 只读 entity_type / concept / sources / source / 标题|title
    (:71 :72 :74 :85 :94),**并不读** okf 注入的 type / stale_after,
    所以先后顺序目前对索引内容没有影响。

    测试保留,但理由改成**防御性**的:一旦索引哪天开始消费 type,顺序反了就会读到
    上一轮的旧字段 —— 那种 bug 极难察觉,不如现在就把顺序钉死。
    """
    src = (REPO / "scripts" / "compile.sh").read_text(encoding="utf-8")
    i_fix = src.find("okf.py --fix")
    i_idx = src.find("build-index.py")
    i_chk = src.find("okf.py --check")
    assert i_fix >= 0, "compile.sh 未接入 okf.py --fix"
    assert i_chk >= 0, "compile.sh 未接入 okf.py --check"
    assert i_fix < i_idx, "注入应在重建 index 之前(防御性约定,见本函数 docstring)"
    assert i_chk > i_idx, "体检应在 lint 记账阶段(index 之后)"
