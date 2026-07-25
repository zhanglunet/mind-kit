#!/usr/bin/env python3
# scripts/evaluate_quality.py —— 认知边界质量断言 runner(P0-2a)。
# 机制借鉴同类项目实践:质量 golden case(自行实现):case 对某页断言
# required_tokens(必须出现,含"限定语原文"如「不据此推断…」)与 forbidden_tokens
# (不得出现的过度推断句)——LLM 是否过度声明变成 grep 可检。
#
# 用法:python3 scripts/evaluate_quality.py <cases.json> [--base DIR] [--allow-missing] [--json]
# 文件缺失默认判失败;--allow-missing 降级为跳过(容器/CI 中 vault 软链缺席时用)。
# 退出码:0 全过;1 有失败;2 用法/文件错误。
import argparse
import json
import sys
from pathlib import Path

SCHEMA = "eval-quality-1"


def eval_case(case, base: Path, allow_missing: bool):
    p = base / case["path"]
    if not p.exists():
        status = "skipped" if allow_missing else "failed"
        return {"id": case.get("id"), "status": status,
                "detail": f"文件不存在:{case['path']}"}
    try:
        text = p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return {"id": case.get("id"), "status": "failed",
                "detail": f"非 UTF-8:{case['path']}"}
    problems = []
    for t in case.get("required_tokens", []):
        if t not in text:
            problems.append(f"缺少必需断言「{t}」")
    # forbidden 检查前先遮蔽 required 的出现位置:限定语(如「不据此推断转型已经成功」)
    # 内含的子串不算违规;forbidden 在限定语之外独立出现才失败。
    masked = text
    for t in case.get("required_tokens", []):
        masked = masked.replace(t, "\0" * len(t))
    for t in case.get("forbidden_tokens", []):
        if t in masked:
            problems.append(f"出现禁止表述「{t}」")
    if problems:
        return {"id": case.get("id"), "status": "failed", "detail": ";".join(problems)}
    return {"id": case.get("id"), "status": "passed", "detail": "ok"}


def main() -> int:
    ap = argparse.ArgumentParser(description="认知边界质量评测")
    ap.add_argument("cases")
    ap.add_argument("--base", default=".", help="case path 的基准目录(默认当前目录)")
    ap.add_argument("--allow-missing", action="store_true")
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
    cases = data.get("cases") or []
    if not cases:
        print("✗ case 文件里没有任何 case(键名拼错或列表为空)——0 条断言不构成基线,拒绝绿灯。",
              file=sys.stderr)
        return 2

    base = Path(args.base)
    results = [eval_case(c, base, args.allow_missing) for c in cases]
    passed = sum(1 for r in results if r["status"] == "passed")
    failed = sum(1 for r in results if r["status"] == "failed")
    skipped = sum(1 for r in results if r["status"] == "skipped")
    report = {"total": len(results), "passed": passed, "failed": failed,
              "skipped": skipped, "ok": failed == 0, "results": results}
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=1))
    else:
        for r in results:
            mark = {"passed": "✓", "failed": "✗", "skipped": "⊘"}[r["status"]]
            print(f"{mark} {r['id']}: {r['detail']}")
        print(f"—— {passed} 过 / {failed} 败 / {skipped} 跳")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
