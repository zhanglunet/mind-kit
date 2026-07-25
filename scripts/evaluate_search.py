#!/usr/bin/env python3
# scripts/evaluate_search.py —— 检索回归 runner(P0-1b)。
# 机制借鉴同类项目实践:golden-case 评测(自行实现,未复制其代码)。
#
# 两个后端:
#   fixture(默认):case 文件内嵌语料(自包含、可在 CI 确定性复现),用内置参考打分器
#     (BM25 + CJK bigram)排名,断言 expected_top1 / expected_in_top3 / forbidden_top1 /
#     expect_no_results,并对排名类 case 计算 MRR。
#   brain:POST http://127.0.0.1:<port>/api/query(brain-server 需在跑),引擎返回文本答案,
#     断言 expected_cite(答案引用期望页/关键词)/ forbidden_cite / expect_no_results(hit=false)。
#     真实 vault 的回归 case 用这个后端,落 mind-vault/evaluation/(含个人内容,不进代码库)。
#
# 用法:python3 scripts/evaluate_search.py <cases.json> [--backend fixture|brain]
#       [--port 8788] [--min-mrr 0.75] [--json]
# 退出码:0 全过且 MRR 达标;1 有失败或 MRR 不达标;2 用法/文件错误。
import argparse
import http.client
import json
import math
import re
import sys
import urllib.request
from collections import Counter
from pathlib import Path

SCHEMA = "eval-retrieval-1"
TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.+-]*|[一-鿿]+")
CJK_RE = re.compile(r"[一-鿿]")


def tokenize(text: str) -> "list[str]":
    """拉丁词整词;中文串 ≤12 字整串保留,另滑窗切出全部相邻二字 bigram(子串召回)。"""
    toks = []
    for run in TOKEN_RE.findall(text.lower()):
        if CJK_RE.match(run):
            if len(run) <= 12:
                toks.append(run)
            toks += [run[i:i + 2] for i in range(len(run) - 1)]
        else:
            toks.append(run)
    return toks


def rank_corpus(corpus, query, k1=1.5, b=0.75) -> "list[str]":
    """参考打分器:标准 BM25,返回得分 >0 的文档 path 降序列表。"""
    docs = [(d["path"], Counter(tokenize(d.get("title", "") + " " + d["content"])))
            for d in corpus]
    n = len(docs) or 1
    avg_len = sum(sum(c.values()) for _, c in docs) / n or 1.0
    q_terms = set(tokenize(query))
    df = Counter(t for _, c in docs for t in set(c) if t in q_terms)
    scored = []
    for path, c in docs:
        dl = sum(c.values())
        s = 0.0
        for t in q_terms:
            tf = c.get(t, 0)
            if not tf:
                continue
            idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
            s += idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * dl / avg_len))
        if s > 0:
            scored.append((s, path))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [p for _, p in scored]


ASSERTION_FIELDS = ("expected_top1", "expected_in_top3", "forbidden_top1",
                    "expect_no_results", "expected_cite", "forbidden_cite")


def _assertion_conflict(case):
    """一个 case 只允许一个断言字段;多个并存不静默取其一,判配置错误。"""
    present = [f for f in ASSERTION_FIELDS if f in case]
    if len(present) > 1:
        return {"id": case.get("id"), "ok": False,
                "detail": f"case 含多个断言字段 {present},每条 case 只允许一个断言"}
    return None


def eval_fixture_case(case, corpus):
    conflict = _assertion_conflict(case)
    if conflict:
        return conflict, None
    return eval_ranked(case, rank_corpus(corpus, case["query"]))


def eval_local_case(case, idx):
    """local 后端(P1-1):用 searchlib(bigram 索引 + 同义扩展 + RRF)出排名,断言同 fixture。"""
    conflict = _assertion_conflict(case)
    if conflict:
        return conflict, None
    import searchlib
    ranking = [r["path"] for r in searchlib.search(idx, case["query"], limit=50)]
    return eval_ranked(case, ranking)


def eval_ranked(case, ranking):
    rr = None
    if "expected_top1" in case or "expected_in_top3" in case:
        want = case.get("expected_top1") or case.get("expected_in_top3")
        pos = ranking.index(want) + 1 if want in ranking else 0
        rr = 1.0 / pos if pos else 0.0
    if "expected_top1" in case:
        ok = bool(ranking) and ranking[0] == case["expected_top1"]
        detail = f"top1={ranking[0] if ranking else '(空)'}"
    elif "expected_in_top3" in case:
        ok = case["expected_in_top3"] in ranking[:3]
        detail = f"top3={ranking[:3]}"
    elif "forbidden_top1" in case:
        ok = not ranking or ranking[0] != case["forbidden_top1"]
        detail = f"top1={ranking[0] if ranking else '(空)'}"
    elif case.get("expect_no_results"):
        ok = not ranking
        detail = f"命中 {len(ranking)} 篇"
    else:
        return {"id": case.get("id"), "ok": False, "detail": "case 缺少断言字段"}, rr
    return {"id": case.get("id"), "ok": ok, "detail": detail}, rr


def query_brain(port, q, timeout=630):
    # eval:true 声明评测流量:brain-server 据此不写调用记账(_wiki/log.md),调用率不掺水
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/query",
        data=json.dumps({"q": q, "eval": True}).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def eval_brain_case(case, port):
    conflict = _assertion_conflict(case)
    if conflict:
        return conflict
    r = query_brain(port, case["query"])
    if not isinstance(r, dict):
        return {"id": case.get("id"), "ok": False, "detail": "brain 响应不是 JSON 对象"}
    answer, hit = str(r.get("answer") or ""), bool(r.get("hit"))
    if "expected_cite" in case:
        ok = hit and case["expected_cite"] in answer
        detail = "已引用" if ok else f"答案未含「{case['expected_cite']}」"
    elif "forbidden_cite" in case:
        ok = case["forbidden_cite"] not in answer
        detail = "未引用禁止页" if ok else f"答案引用了「{case['forbidden_cite']}」"
    elif case.get("expect_no_results"):
        ok = not hit
        detail = f"hit={hit}"
    else:
        return {"id": case.get("id"), "ok": False, "detail": "case 缺少 brain 后端断言字段"}
    return {"id": case.get("id"), "ok": ok, "detail": detail}


def main() -> int:
    ap = argparse.ArgumentParser(description="检索回归评测")
    ap.add_argument("cases")
    ap.add_argument("--backend", choices=["fixture", "brain", "local"], default="fixture")
    ap.add_argument("--vault", default=None,
                    help="local 后端在 fixture 无 corpus 时索引的 vault 根(默认仓库根)")
    ap.add_argument("--port", type=int, default=8788)
    ap.add_argument("--min-mrr", type=float, default=0.75)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    try:
        data = json.loads(open(args.cases, encoding="utf-8").read())
    except (OSError, ValueError) as e:
        print(f"✗ 无法读取 case 文件:{e}", file=sys.stderr)
        return 2
    if data.get("schema_version") != SCHEMA:
        print(f"✗ schema_version 应为 {SCHEMA}", file=sys.stderr)
        return 2
    case_list = data.get("cases") or []
    if not case_list:
        print("✗ case 文件里没有任何 case(键名拼错或列表为空)——0 条断言不构成基线,拒绝绿灯。",
              file=sys.stderr)
        return 2

    local_idx = None
    if args.backend == "local":
        import searchlib
        corpus = data.get("corpus") or []
        # fixture 有内嵌语料则评语料;否则对真实 vault 建索引(本机跑真实回归用)
        vault = Path(args.vault) if args.vault else Path(__file__).resolve().parent.parent
        local_idx = searchlib.build_index(corpus) if corpus else searchlib.get_index(vault)
        if not local_idx["entries"]:
            print(f"✗ local 后端索引输入面为空(corpus 缺失且 {vault} 下无 _wiki/material 页面"
                  f"——目录缺失或软链未挂?)。空索引评测会假绿,拒绝执行。", file=sys.stderr)
            return 2

    results, rrs = [], []
    for case in case_list:
        if args.backend == "fixture":
            res, rr = eval_fixture_case(case, data.get("corpus", []))
            if rr is not None:
                rrs.append(rr)
        elif args.backend == "local":
            res, rr = eval_local_case(case, local_idx)
            if rr is not None:
                rrs.append(rr)
        else:
            try:
                res = eval_brain_case(case, args.port)
            except (OSError, ValueError, http.client.HTTPException) as e:
                # OSError=连接/超时;ValueError=响应非 JSON;HTTPException=协议异常。
                # 单个坏响应只判该 case 失败,不崩掉整个 suite 的报告。
                res = {"id": case.get("id"), "ok": False,
                       "detail": f"brain 请求/响应异常:{type(e).__name__}: {e}"}
        results.append(res)

    passed = sum(1 for r in results if r["ok"])
    failed = len(results) - passed
    mrr = round(sum(rrs) / len(rrs), 4) if rrs else None
    ok = failed == 0 and (mrr is None or mrr >= args.min_mrr)
    report = {"backend": args.backend, "total": len(results), "passed": passed,
              "failed": failed, "mrr": mrr, "min_mrr": args.min_mrr,
              "ok": ok, "results": results}
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=1))
    else:
        for r in results:
            print(f"{'✓' if r['ok'] else '✗'} {r['id']}: {r['detail']}")
        print(f"—— {passed}/{len(results)} 过" + (f",MRR={mrr}" if mrr is not None else ""))
        if failed == 0 and mrr is not None and mrr < args.min_mrr:
            print(f"✗ MRR {mrr} < 门槛 {args.min_mrr}:断言虽全过,但期望页排名偏后,整体判不达标。")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
