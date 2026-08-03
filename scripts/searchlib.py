# scripts/searchlib.py —— 本地检索库(P1-1 检索栈升级,FR-QRY-06)。
# 机制借鉴同类项目实践:(索引级 CJK bigram / 多通道 RRF / 同义组扩展),自行实现。
#
# 分工:sage-wiki 引擎负责 LLM 综合问答(慢、贵);本库负责**秒级本地排名检索**——
# brain-server 的 /api/search 用它,评测 --backend local 用它,引擎兜底重查用它的同义扩展。
# 设计取舍:本库 ~数百页,索引全量重建 <1s → 内存缓存 + 指纹自动刷新即可,
# 不做 delta 覆盖层(逐文件 sha256 清单已留好地基,库过数千页再上)。
import hashlib
import math
import re
from collections import Counter
from pathlib import Path

import indexlib

TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.+-]*|[一-鿿]+")
CJK_RE = re.compile(r"[一-鿿]")

# 双语同义组(P1-1c):命中任一词,则把组内其它词追加为检索词。
# 纪律:**扩展只造检索词,不造事实**——只影响召回,不进入任何产出内容。
SYNONYM_GROUPS = [
    {"冲突", "矛盾", "conflict", "contradict"},
    {"检索", "搜索", "search", "retrieval"},
    {"保鲜", "新鲜度", "freshness"},
    {"复利", "compounding"},
    {"知识库", "wiki"},
    {"评测", "评估", "evaluation"},
    {"索引", "index"},
    {"大模型", "llm"},
    {"智能体", "agent"},
    {"提示词", "prompt"},
    {"部署", "deploy", "deployment"},
    {"离线", "offline"},
    {"编译", "compile"},
    {"半衰期", "half-life"},
]


def tokenize(text: str) -> "list[str]":
    """索引级分词(P1-1a):拉丁整词小写;中文串 ≤12 字整串保留 + 全部相邻二字 bigram。"""
    toks = []
    for run in TOKEN_RE.findall(text.lower()):
        if CJK_RE.match(run):
            if len(run) <= 12:
                toks.append(run)
            toks += [run[i:i + 2] for i in range(len(run) - 1)]
        else:
            toks.append(run)
    return toks


def expand_query(query: str) -> str:
    """同义组扩展:命中组内任一词则追加组内未出现的其它词;无命中原样返回。
    匹配规则(评审修复):**拉丁词按整词(token)匹配**——裸子串会误命中
    ("search"⊂"research"、"agent"⊂"reagent",实测能翻转 top1);
    中文词保留子串匹配(中文无词边界,bigram 分词本就会命中,收紧无意义)。"""
    low = query.lower()
    latin_tokens = {t for t in tokenize(query) if not CJK_RE.match(t)}
    extra = []

    def hit(term: str) -> bool:
        return (term in low) if CJK_RE.search(term) else (term in latin_tokens)

    def present(term: str) -> bool:
        return (term in low) if CJK_RE.search(term) else (term in latin_tokens)

    for group in SYNONYM_GROUPS:
        if any(hit(t) for t in group):
            extra += [t for t in sorted(group) if not present(t) and t not in extra]
    return query if not extra else query + " " + " ".join(extra)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def make_snippet(content: str, limit: int = 120) -> str:
    """给人看的一行摘要:跳过 frontmatter 与标题行,取真正的正文。

    别用 content[:120] —— 库里页面普遍以 10+ 行 frontmatter 开头,那样摘出来的
    全是「类别:/来源:/tags」这类机器字段(还会把 frontmatter 里的 token 一起带出去,
    2026-07-26 实测泄进过飞书聊天窗口)。召回不受影响:分词仍吃全文。
    """
    text = content or ""
    if text.startswith("---"):                      # YAML frontmatter:掐到第二个 ---
        end = text.find("\n---", 3)
        if end != -1:
            text = text[end + 4:]
    lines = [ln.strip() for ln in text.splitlines()]
    body = [ln for ln in lines if ln and not ln.startswith("#")]
    if not body:                                    # 只有 frontmatter/标题 → 退回原文压平
        body = [ln.strip() for ln in (content or "").splitlines() if ln.strip()] or ["(空页)"]
    return " ".join(body)[:limit]


def build_index(docs) -> dict:
    """从 [{path,title,content}] 构建内存索引。
    每文档词袋 = 标题词×2(标题加权)+ 正文词;附逐文件 sha256 清单(P1-1e)与整体指纹。"""
    entries, files = [], {}
    h = hashlib.sha256()
    for d in sorted(docs, key=lambda x: x["path"]):
        title = d.get("title") or Path(d["path"]).stem
        content = d.get("content") or ""
        tf = Counter(tokenize(title)) + Counter(tokenize(title)) + Counter(tokenize(content))
        entries.append({
            "path": d["path"], "title": title,
            "tf": tf, "len": sum(tf.values()),
            "title_tokens": set(tokenize(title)),
            "raw": (title + "\n" + content).lower(),
            "snippet": make_snippet(content),
        })
        files[d["path"]] = _sha256(content)
        h.update(d["path"].encode("utf-8")); h.update(b"\0")
        h.update(content.encode("utf-8")); h.update(b"\0")
    return {"entries": entries, "files": files, "fingerprint": h.hexdigest(),
            "avg_len": (sum(e["len"] for e in entries) / len(entries)) if entries else 1.0}


def _bm25_scores(idx, q_terms, k1=1.5, b=0.75) -> dict:
    n = len(idx["entries"]) or 1
    df = Counter(t for e in idx["entries"] for t in set(e["tf"]) if t in q_terms)
    scores = {}
    for e in idx["entries"]:
        s = 0.0
        for t in q_terms:
            tf = e["tf"].get(t, 0)
            if not tf:
                continue
            idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
            s += idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * e["len"] / idx["avg_len"]))
        if s > 0:
            scores[e["path"]] = s
    return scores


def search(idx, query, limit=20) -> "list[dict]":
    """三通道 RRF(P1-1b):BM25 / 标题·文件名重合 / 短语精确,score += 1/(60+rank)。"""
    expanded = expand_query(query)
    q_terms = set(tokenize(expanded))
    if not q_terms:
        return []
    by_path = {e["path"]: e for e in idx["entries"]}

    channels = {}
    channels["bm25"] = [p for p, _ in sorted(_bm25_scores(idx, q_terms).items(),
                                             key=lambda x: (-x[1], x[0]))]
    title_hits = [(len(q_terms & e["title_tokens"]), e["path"]) for e in idx["entries"]]
    channels["title"] = [p for c, p in sorted(((c, p) for c, p in title_hits if c > 0),
                                              key=lambda x: (-x[0], x[1]))]
    phrase = query.strip().lower()
    channels["phrase"] = ([e["path"] for e in idx["entries"] if len(phrase) >= 4 and phrase in e["raw"]]
                          if phrase else [])

    rrf, hit_channels = {}, {}
    for name, ranked in channels.items():
        for rank, path in enumerate(ranked, 1):
            rrf[path] = rrf.get(path, 0.0) + 1.0 / (60 + rank)
            hit_channels.setdefault(path, []).append(name)
    ordered = sorted(rrf.items(), key=lambda x: (-x[1], x[0]))[:limit]
    return [{"path": p, "title": by_path[p]["title"], "score": round(s, 5),
             "channels": hit_channels[p], "snippet": by_path[p]["snippet"]}
            for p, s in ordered]


# ---------- vault 索引:内存缓存 + 指纹自动刷新 ----------

_CACHE: "dict[str, tuple[str, dict]]" = {}


def get_index(vault) -> dict:
    """对 vault(输入面 = indexlib.browse_inputs,与浏览站一致)建索引;
    内容未变时返回缓存的同一对象,变化时自动重建。"""
    vault = Path(vault)
    files = indexlib.browse_inputs(vault)
    fp = indexlib.input_fingerprint(files, base=vault)["fingerprint"]
    key = str(vault)
    cached = _CACHE.get(key)
    if cached and cached[0] == fp:
        return cached[1]
    docs = []
    for f in files:
        try:
            content = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        rel = str(f.relative_to(vault)) if str(f).startswith(str(vault)) else str(f)
        docs.append({"path": rel, "title": f.stem, "content": content})
    idx = build_index(docs)
    idx["fingerprint"] = fp   # 以文件面指纹为准(与 indexlib/浏览站语义一致)
    _CACHE[key] = (fp, idx)
    return idx
