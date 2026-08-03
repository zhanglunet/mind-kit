"""searchlib 的行为测试(P1-1):索引级 CJK bigram、同义扩展、三通道 RRF、指纹刷新。
契约:
- tokenize:拉丁整词小写;中文串 ≤12 字整串保留 + 全部相邻二字 bigram。
- expand_query:按双语同义组扩展检索词(只造检索词,不造事实);无命中组时原样返回。
- build_index(docs):接受 [{path,title,content}];索引含逐文件内容 sha256(files 键)。
- search:BM25 / 标题·文件名 / 短语精确 三通道 RRF 融合,返回 [{path,title,score,channels,snippet}]。
- index_vault/get_index:输入面 = indexlib.browse_inputs;内容变化后 get_index 自动重建。
"""
from pathlib import Path

import searchlib as S


# ---------- tokenize ----------

def test_tokenize_latin_and_cjk_bigram():
    toks = S.tokenize("BM25 检索质量")
    assert "bm25" in toks
    assert "检索" in toks and "索质" in toks and "质量" in toks     # bigram 滑窗
    assert "检索质量" in toks                                       # ≤12 字整串保留


def test_tokenize_long_cjk_run_only_bigrams():
    run = "这是一个超过十二个字的超长中文串共十六字"
    toks = S.tokenize(run)
    assert run not in toks                    # >12 字不保整串
    assert "这是" in toks and "六字" in toks   # bigram 覆盖首尾


# ---------- expand_query ----------

def test_expand_query_bilingual_groups():
    ex = S.expand_query("冲突 检测")
    assert "conflict" in ex                    # 中文→英文同义
    ex2 = S.expand_query("freshness check")
    assert "保鲜" in ex2                       # 英文→中文同义


def test_expand_query_no_group_passthrough():
    assert S.expand_query("量子海鲜") == "量子海鲜"


def test_expand_query_latin_token_boundary_no_false_trigger():
    # 评审确认问题:拉丁词裸子串匹配会误命中("search" ⊂ "research"、"agent" ⊂ "reagent"),
    # 且实测能翻转 top1。拉丁词必须按整词(token)匹配;整词出现仍应扩展。
    assert S.expand_query("research funding") == "research funding"   # 不得加 检索/retrieval
    assert S.expand_query("reagent 采购") == "reagent 采购"            # 不得加 智能体
    assert "检索" in S.expand_query("search 功能")                     # 整词命中仍扩展
    assert "deploy" in S.expand_query("deployment guide")             # 组内异词整词命中 → 补组内其它词


# ---------- 索引与检索 ----------

DOCS = [
    {"path": "_wiki/concepts/冲突标注.md", "title": "冲突标注",
     "content": "Conflict detection: when two sources contradict, mark the conflict explicitly."},
    {"path": "_wiki/concepts/标注工具.md", "title": "标注工具",
     "content": "标注工具的使用指南:如何给图片打标注、管理标注标签、导出标注结果。"},
    {"path": "_wiki/outputs/五维决策看板.md", "title": "五维决策看板",
     "content": "看板页,汇总入口。"},
    {"path": "_wiki/concepts/决策方法.md", "title": "决策方法",
     "content": "决策决策决策,维度维度,方法方法方法,反复讨论决策的维度与方法细节。"},
    {"path": "_wiki/concepts/星图编译.md", "title": "星图编译",
     "content": "星图编译把笔记编译为互联页面,编译一次持续保鲜,知识持续增值。"},
]


def test_build_index_has_per_file_manifest():
    idx = S.build_index(DOCS)
    assert set(idx["files"]) == {d["path"] for d in DOCS}
    assert all(len(v) == 64 for v in idx["files"].values())    # sha256 逐文件清单(P1-1e)


def test_search_synonym_expansion_wins():
    # 查询「冲突 标注」:冲突页只有英文 conflict——旧纯 BM25 会让“标注工具”霸榜;
    # 同义扩展(冲突→conflict)后冲突标注页应登顶
    idx = S.build_index(DOCS)
    top = S.search(idx, "冲突 标注")
    assert top and top[0]["path"] == "_wiki/concepts/冲突标注.md", top[:2]


def test_search_title_channel_beats_tf_stuffing():
    # 查询恰为标题「五维决策看板」:内容堆砌“决策/维度”的页不得压过精确标题页
    idx = S.build_index(DOCS)
    top = S.search(idx, "五维决策看板")
    assert top and top[0]["path"] == "_wiki/outputs/五维决策看板.md", top[:2]


def test_search_phrase_channel():
    # 精确短语「编译一次持续保鲜」原文出现的页应登顶
    idx = S.build_index(DOCS)
    top = S.search(idx, "编译一次持续保鲜")
    assert top and top[0]["path"] == "_wiki/concepts/星图编译.md", top[:2]


def test_search_english_query_hits_chinese_doc():
    # 纯英文查询经同义组落到中文页(freshness→保鲜)
    idx = S.build_index(DOCS)
    top = S.search(idx, "freshness")
    assert top and top[0]["path"] == "_wiki/concepts/星图编译.md", top[:2]


def test_search_no_results_for_fabricated():
    idx = S.build_index(DOCS)
    assert S.search(idx, "量子海鲜反应堆手册") == []


def test_search_result_shape():
    idx = S.build_index(DOCS)
    r = S.search(idx, "标注 工具")[0]
    assert {"path", "title", "score", "channels", "snippet"} <= set(r)


# ---------- vault 索引与自动刷新 ----------

def _mk(base: Path, rel: str, text: str):
    p = base / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_get_index_auto_refresh_on_change(tmp_path):
    _mk(tmp_path, "_wiki/concepts/甲.md", "初始内容:关于检索的页面。")
    idx1 = S.get_index(tmp_path)
    assert S.search(idx1, "初始 检索")
    _mk(tmp_path, "_wiki/concepts/乙.md", "新增页面:讲评测基线。")
    idx2 = S.get_index(tmp_path)                      # 内容变化 → 自动重建
    assert S.search(idx2, "评测 基线")
    assert idx1["fingerprint"] != idx2["fingerprint"]


def test_get_index_cached_when_unchanged(tmp_path):
    _mk(tmp_path, "material/quotes/句.md", "金句内容。")
    a = S.get_index(tmp_path)
    b = S.get_index(tmp_path)
    assert a is b                                      # 未变化 → 同一对象(缓存命中)
