# -*- coding: utf-8 -*-
"""PRD-387/T2（trend issue #1891 的 T2 环节）：入库知识验证台最小实现。

按 T1 设计（docs/prd/2026-11-12-prd-387-knowledge-verification-bench-design.md）
§4 落地：

  - verify_knowledge(item, corpus, recheck_fn)：逐条知识来源复核验证
    ——recheck_fn 注入式重跑同一来源复核判定（语料快照只读深拷贝，零真实
    外呼 R2）；来源在语料中可复访（source_match）+ quote 逐字回指
    （quote_match）双 match → VERIFIED，否则 UNVERIFIED（词表封闭）；
    语料指纹 sha16: 前缀确定性；
  - verify_items(items, corpus, recheck_fn)：入库来源包装（接入点：知识
    入库入口，build-index.py 消费 wiki 源之前）——UNVERIFIED 拦下不进
    Wiki（R1）；
  - KnowledgeBenchLedger：机器可读 JSONL 落账（路径注入，append-only
    R3/R4）；八件套缺一 BENCH_INCOMPLETE 拒绝入账；
  - reverify：语料变更二次验证——指纹不符 → BENCH_STALE 拒绝复用旧验证
    （R4 关闭以最新 VERIFIED 为准）。

零网络零子进程（复访=对语料快照复算）；示例 URL 一律 example.invalid；
示例全虚构占位。
测试：tests/test_knowledge_verify_bench.py
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Callable

BENCH_SCHEMA = "knowledge-verify-bench/v1"
VERDICTS = ("VERIFIED", "UNVERIFIED")
ERROR_CODES = ("BENCH_INCOMPLETE", "BENCH_REPRO_MISMATCH", "BENCH_STALE")


class KnowledgeBenchError(ValueError):
    """验证台违规——显形拒绝。"""


def corpus_fingerprint(corpus: Any) -> str:
    """语料快照指纹（sha16: 前缀，canonical JSON 确定性摘要）。"""
    canon = json.dumps(corpus, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"))
    return "sha16:" + hashlib.sha256(canon.encode("utf-8")).hexdigest()[:16]


def _recusal(code: str, detail: str) -> dict[str, Any]:
    return {"schema": BENCH_SCHEMA, "refused": code, "detail": detail,
            "verdict": None}


def verify_knowledge(item: dict[str, Any], corpus: Any,
                     recheck_fn: Callable[[Any], list[dict[str, Any]]],
                     *, at: str = "") -> dict[str, Any]:
    """逐条知识来源复核验证（R1/R2）：复访+quote 回指双 match → VERIFIED。"""
    if not isinstance(item, dict):
        return _recusal("BENCH_INCOMPLETE", "item 非对象")
    missing = [k for k in ("item_id", "source_url", "kind", "source_ref",
                           "quote") if not item.get(k)]
    if missing:
        return _recusal("BENCH_INCOMPLETE", f"八件套缺 {missing}")
    if not callable(recheck_fn):
        return _recusal("BENCH_INCOMPLETE", "recheck_fn 未注入")
    rerun = recheck_fn(copy.deepcopy(corpus)) or []
    sm = any(str(r.get("source_url")) == str(item.get("source_url"))
             for r in rerun) and any(str(c.get("url") or "") ==
                                     str(item.get("source_url"))
                                     for c in (corpus or []))
    qm = bool(item["quote"]) and any(str(item["quote"]) in str(c.get("text") or "")
                                     for c in (corpus or []))
    ok = sm and qm
    return {
        "schema": BENCH_SCHEMA,
        "item_id": item["item_id"],
        "source_url": item["source_url"],
        "kind": item["kind"],
        "source_ref": item["source_ref"],
        "corpus_fingerprint": corpus_fingerprint(corpus),
        "item": copy.deepcopy(item),
        "reproduce": {"source_match": sm, "quote_match": qm,
                      "detail": f"重跑复核 {len(rerun)} 条（占位）"},
        "verdict": "VERIFIED" if ok else "UNVERIFIED",
        "at": at,
    }


def verify_items(items: list[dict[str, Any]], corpus: Any,
                 recheck_fn: Callable[[Any], list[dict[str, Any]]],
                 *, at: str = "") -> dict[str, Any]:
    """入库来源包装（接入点）：UNVERIFIED 拦下不进 Wiki（R1）。"""
    verified: list[dict[str, Any]] = []
    unverified: list[dict[str, Any]] = []
    for i in items or []:
        out = verify_knowledge(i, corpus, recheck_fn, at=at)
        if out.get("refused") or out["verdict"] == "UNVERIFIED":
            unverified.append(out)
        else:
            verified.append(out)
    return {"schema": BENCH_SCHEMA, "verified": verified,
            "unverified": unverified, "unverified_count": len(unverified)}


class KnowledgeBenchLedger:
    """验证账本（R3/R4）：JSONL append-only；八件套缺一拒绝入账。"""

    _REQUIRED = ("item_id", "source_url", "kind", "source_ref",
                 "corpus_fingerprint", "item", "verdict")

    def __init__(self, path: str | Path | None = None) -> None:
        self._records: list[dict[str, Any]] = []
        self._path = Path(path) if path else None

    def record(self, out: dict[str, Any], *, at: str = "") -> dict[str, Any]:
        if out.get("refused"):
            raise KnowledgeBenchError(f"{out['refused']}：{out['detail']}")
        rec = dict(out, at=at)
        missing = [k for k in self._REQUIRED if rec.get(k) in (None, "")]
        if missing:
            raise KnowledgeBenchError(f"BENCH_INCOMPLETE：账目缺 {missing}")
        if rec["verdict"] not in VERDICTS:
            raise KnowledgeBenchError(f"BENCH_INCOMPLETE：verdict 词表外 "
                                      f"{rec['verdict']!r}")
        rep = rec["reproduce"]
        if rec["verdict"] == "VERIFIED" and not (rep.get("source_match")
                                                 and rep.get("quote_match")):
            raise KnowledgeBenchError("BENCH_REPRO_MISMATCH：声称 VERIFIED 但"
                                      "复现不全——验证结论与复现证据不一致")
        self._records.append(copy.deepcopy(rec))
        if self._path is not None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False,
                                    sort_keys=True) + "\n")
        return dict(rec)

    def entries(self) -> list[dict[str, Any]]:
        return [dict(r) for r in self._records]

    def latest_for(self, item_id: str) -> dict[str, Any] | None:
        found = [r for r in self._records if r["item_id"] == item_id]
        return dict(found[-1]) if found else None

    def reverify(self, item_id: str, corpus: Any,
                 recheck_fn: Callable[[Any], list[dict[str, Any]]],
                 *, at: str = "") -> dict[str, Any]:
        """语料变更二次验证（R4）：指纹不符 → BENCH_STALE 拒绝复用。"""
        prior = self.latest_for(item_id)
        fp_now = corpus_fingerprint(corpus)
        if prior and prior["corpus_fingerprint"] != fp_now:
            return _recusal("BENCH_STALE",
                            f"{item_id} 旧验证语料指纹与当前不符——语料变更后"
                            "须重新验证，旧 VERIFIED 不复用")
        base = {"item_id": item_id,
                "source_url": (prior or {}).get("source_url") or "",
                "kind": (prior or {}).get("kind") or "",
                "source_ref": (prior or {}).get("source_ref") or "",
                "quote": ((prior or {}).get("item") or {}).get("quote")}
        return self.record(verify_knowledge(base, corpus, recheck_fn, at=at),
                           at=at)
