#!/usr/bin/env python3
# scripts/decision.py —— 待确认决策队列(P1-2,FR-SCH-06)。
# 机制借鉴同类项目实践:decision-record + 单一用户入口(自行实现):
# 须先确认的动作(提升入库/删除/合并/Schema 变更)每件一条决策记录,
# 状态机 pending → approved|rejected|deferred → applied;
# **approved 只代表用户授权,实际执行完成后才 apply**(审批与执行分离,均可追溯)。
#
# 记录落 <vault>/_wiki/outputs/decisions/(outputs 是 LLM 领地;经软链落 mind-vault);
# 唯一用户入口 <vault>/_wiki/outputs/待确认看板.md(Dataview 聚合,机器记录不双写)。
#
# 用法:
#   decision.py new <type> "<标题>" [--target 页面] [--recommend 建议]   建记录(pending)
#   decision.py list [--status pending] [--json]                          列记录
#   decision.py approve <DEC-id> [--note 说明] / reject / defer           用户裁决
#   decision.py apply <DEC-id>                                            执行完成后落章
#   decision.py check                                                     不变量校验(lint 用,违规非零退出)
#   decision.py board                                                     幂等生成入口看板页
# 退出码:0 成功;1 非法迁移/校验失败;2 用法错误。
import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

TYPES = ("promote", "merge", "delete", "schema", "archive", "other")
STATUSES = ("pending", "approved", "rejected", "deferred", "applied")
# 动作 → (允许的当前状态, 目标状态)
TRANSITIONS = {
    "approve": ({"pending", "deferred"}, "approved"),
    "reject": ({"pending", "deferred"}, "rejected"),
    "defer": ({"pending"}, "deferred"),
    "apply": ({"approved"}, "applied"),
}
ID_RE = re.compile(r"^DEC-\d{8}-\d{2,}$")   # 序号 2 位起步,同日超 99 条自然进位


def yaml_val(v: str) -> str:
    """值的 YAML 安全写法:含冒号/井号/引号/首尾空白时用 JSON 双引号标量(合法 YAML 子集)。
    评审确认:裸拼「title: P1-2: xxx」不是合法 YAML,Dataview 解析失败 → 记录在看板静默隐身。"""
    if v and not re.search(r'[:#"]|^\s|\s$', v):
        return v
    return json.dumps(v, ensure_ascii=False)


def unyaml_val(v: str) -> str:
    if v.startswith('"'):
        try:
            return json.loads(v)
        except ValueError:
            pass
    return v


def guard_oneline(name: str, v: str) -> "str | None":
    """值不得含换行(frontmatter 行注入面,评审确认可伪造 decision_status)。"""
    if "\n" in v or "\r" in v:
        return f"✗ {name} 不得包含换行(frontmatter 行注入风险)"
    return None

BOARD = """---
title: 待确认看板
dimension: [人与组织]
---

# 待确认看板

> 唯一用户入口:所有等待你裁决的事项都聚合在这里(记录本体在 `decisions/` 子目录,不双写)。
> 裁决方式:告诉 Claude「批准/拒绝/缓议 DEC-xxx」,或 `python3 scripts/decision.py approve <id>`。
> **批准 ≠ 完成**:approved 只是授权;实际执行完成后记录才会变为 applied。

## 待处理

```dataview
TABLE decision_type AS 类型, target AS 涉及页面, created AS 创建日
FROM "_wiki/outputs/decisions"
WHERE decision_status = "pending" OR decision_status = "deferred"
SORT created DESC
```

## 已批准待执行

```dataview
TABLE decision_type AS 类型, target AS 涉及页面, decided_at AS 批准日
FROM "_wiki/outputs/decisions"
WHERE decision_status = "approved"
SORT decided_at DESC
```

## 已完结(最近)

```dataview
TABLE decision_status AS 结果, decided_at AS 裁决日, applied_at AS 执行日
FROM "_wiki/outputs/decisions"
WHERE decision_status = "applied" OR decision_status = "rejected"
SORT decided_at DESC
LIMIT 20
```
"""


def records_dir(vault: Path) -> Path:
    return vault / "_wiki" / "outputs" / "decisions"


def parse(path: Path) -> dict:
    text = path.read_text(encoding="utf-8-sig")   # utf-8-sig:吃掉 Windows 编辑器加的 BOM
    fm = {}
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                fm[k.strip()] = unyaml_val(v.strip())
    return {"path": path, "text": text, **fm}


def load_all(vault: Path) -> "list[dict]":
    d = records_dir(vault)
    return [parse(p) for p in sorted(d.glob("*.md"))] if d.is_dir() else []


def set_fm(text: str, key: str, value: str) -> str:
    """frontmatter 里改/插一个键(插在 decision_status 行后)。
    评审修复两处:①只在 fm 块内查改——全文正则会误改正文里行首的字段名(实测覆盖 recommend 原文);
    ②replacement 用 lambda——值含反斜杠/\\1/\\g<0> 时 f-string replacement 会崩溃或注入。"""
    m = re.match(r"^(---\n.*?\n---\n)(.*)$", text, re.S)
    if not m:
        return text
    fm, body = m.group(1), m.group(2)
    line = f"{key}: {yaml_val(value)}"
    if re.search(rf"(?m)^{key}:", fm):
        fm = re.sub(rf"(?m)^{key}:.*$", lambda _: line, fm, count=1)
    else:
        fm = re.sub(r"(?m)^(decision_status:.*)$", lambda mm: mm.group(1) + "\n" + line, fm, count=1)
    return fm + body


def _seq_of(s: str) -> int:
    m = re.search(r"-(\d+)$", s)
    return int(m.group(1)) if m else 0


def cmd_new(args, vault: Path) -> int:
    if args.type not in TYPES:
        print(f"✗ type 须为 {TYPES} 之一", file=sys.stderr)
        return 2
    for name, v in (("title", args.title), ("target", args.target), ("recommend", args.recommend)):
        err = guard_oneline(name, v)
        if err:
            print(err, file=sys.stderr)
            return 2
    d = records_dir(vault)
    d.mkdir(parents=True, exist_ok=True)
    today = date.today().strftime("%Y%m%d")
    # 序号双源扫描:记录 frontmatter 的 decision_id + 文件名前缀兜底(防 BOM/坏 fm 导致复用)
    used = [_seq_of(r.get("decision_id", "")) for r in load_all(vault)
            if r.get("decision_id", "").startswith(f"DEC-{today}-")]
    used += [_seq_of("-".join(p.stem.split("-")[:3])) for p in d.glob(f"DEC-{today}-*.md")]
    seq = 1 + max(used, default=0)
    did = f"DEC-{today}-{seq:02d}"
    slug = re.sub(r"[^\w一-鿿-]+", "-", args.title).strip("-")[:40] or "决策"
    body = f"""---
title: {yaml_val(args.title)}
decision_id: {did}
decision_type: {args.type}
decision_status: pending
target: {yaml_val(args.target) if args.target else ""}
created: {date.today().isoformat()}
---

# {args.title}

## 需要决定

(一句话说清要用户裁决什么。)

## 建议及依据

{args.recommend or "(Agent 的建议与理由。)"}

## 可选项与影响

- 批准:
- 拒绝:
- 缓议:

## 用户决策

(裁决后由 approve/reject/defer 记录。)
"""
    (d / f"{did}-{slug}.md").write_text(body, encoding="utf-8")
    print(f"✅ 已建决策记录 {did}(pending)→ {d / (did + '-' + slug + '.md')}")
    return 0


def _find(vault: Path, did: str) -> "dict | None":
    for r in load_all(vault):
        if r.get("decision_id") == did:
            return r
    return None


def cmd_transition(action: str, args, vault: Path) -> int:
    rec = _find(vault, args.id)
    if not rec:
        print(f"✗ 找不到 {args.id}", file=sys.stderr)
        return 1
    allowed, target = TRANSITIONS[action]
    cur = rec.get("decision_status")
    if cur not in allowed:
        print(f"✗ {args.id} 当前是 {cur},不允许 {action}(须为 {sorted(allowed)};"
              f"注意 approved 只是授权,apply 才代表执行完成)", file=sys.stderr)
        return 1
    note = getattr(args, "note", "") or ""
    err = guard_oneline("note", note)
    if err:
        print(err, file=sys.stderr)
        return 2
    text = set_fm(rec["text"], "decision_status", target)
    if action in ("approve", "reject"):
        text = set_fm(text, "decided_at", date.today().isoformat())
        note = note or ("批准" if action == "approve" else "拒绝")
        text = set_fm(text, "user_decision", note)
        stamp = f"{date.today().isoformat()}:{note}"
        text = re.sub(r"(?m)^\(裁决后由 approve/reject/defer 记录。\)$",
                      lambda _: stamp, text, count=1)   # lambda:note 含 \1 等不注入
    if action == "apply":
        text = set_fm(text, "applied_at", date.today().isoformat())
    rec["path"].write_text(text, encoding="utf-8")
    print(f"✅ {args.id}: {cur} → {target}")
    return 0


def cmd_list(args, vault: Path) -> int:
    rows = [{"decision_id": r.get("decision_id"), "title": r.get("title"),
             "decision_type": r.get("decision_type"), "decision_status": r.get("decision_status"),
             "target": r.get("target"), "created": r.get("created")}
            for r in load_all(vault)
            if not args.status or r.get("decision_status") == args.status]
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=1))
    else:
        for x in rows:
            # or "?":decisions/ 下的外来文件(README 等)无 frontmatter,不得让 list 崩(评审修复)
            print(f"{x['decision_id'] or '?'}  [{(x['decision_status'] or '?'):>8}] "
                  f"{(x['decision_type'] or '?'):<8} {x['title'] or '?'}")
        print(f"—— 共 {len(rows)} 条" + (f"(status={args.status})" if args.status else ""))
    return 0


def record_problems(rec: dict) -> "list[str]":
    """单条决策记录的不变量问题(不含跨记录的 ID 重复检查)。
    供 cmd_check 与 validate_write_set.py(P1-4 写集校验)共用——单一权威实现。"""
    problems = []
    did, st = rec.get("decision_id", "?"), rec.get("decision_status")
    if not ID_RE.match(did):
        problems.append(f"decision_id 格式非法({did})")
    if st not in STATUSES:
        problems.append(f"非法状态 {st}")
    if rec.get("decision_type") not in TYPES:
        problems.append(f"非法 decision_type({rec.get('decision_type')})")
    if st in ("approved", "rejected", "applied") and not rec.get("decided_at"):
        problems.append(f"{st} 但缺 decided_at")
    if st == "applied" and not rec.get("applied_at"):
        problems.append("applied 但缺 applied_at")
    if st == "pending" and (rec.get("user_decision") or rec.get("decided_at") or rec.get("applied_at")):
        problems.append("pending 不得带裁决/执行字段")
    if st == "deferred" and (rec.get("decided_at") or rec.get("applied_at")):
        problems.append("deferred 不得带 decided_at/applied_at(缓议不是裁决)")
    if st != "applied" and rec.get("applied_at"):
        problems.append("未 applied 却有 applied_at")
    return problems


def cmd_check(vault: Path) -> int:
    """不变量校验(供 lint):record_problems 的全库版 + 跨记录 ID 唯一性。"""
    problems, seen = [], {}
    for r in load_all(vault):
        did = r.get("decision_id", "?")
        where = r["path"].name
        if did in seen:
            problems.append(f"{where}: decision_id 与 {seen[did]} 重复({did})")
        seen[did] = where
        problems += [f"{did}: {p}" for p in record_problems(r)]
    for p in problems:
        print(f"✗ {p}", file=sys.stderr)
    print(f"—— check:{len(seen)} 条记录,{len(problems)} 处违规")
    return 1 if problems else 0


def cmd_board(vault: Path) -> int:
    page = vault / "_wiki" / "outputs" / "待确认看板.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    if not page.exists():
        page.write_text(BOARD, encoding="utf-8")
        print(f"✅ 入口看板已创建:{page}")
    elif page.read_text(encoding="utf-8") != BOARD:
        # 唯一用户入口页,用户可能写了批注:不覆盖(评审修复;要重置手动删除后重跑 board)
        print(f"ℹ️ 看板已存在且含本地改动,未覆盖:{page}")
    else:
        print(f"✅ 入口看板就绪:{page}")
    return 0


def main() -> int:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--vault", default=None, help="vault 根(默认仓库根;测试用)")
    ap = argparse.ArgumentParser(description="待确认决策队列")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_new = sub.add_parser("new", parents=[common])
    p_new.add_argument("type"); p_new.add_argument("title")
    p_new.add_argument("--target", default=""); p_new.add_argument("--recommend", default="")
    p_list = sub.add_parser("list", parents=[common])
    p_list.add_argument("--status", default="", choices=("",) + STATUSES)
    p_list.add_argument("--json", action="store_true")
    for a in TRANSITIONS:
        p = sub.add_parser(a, parents=[common]); p.add_argument("id")
        if a in ("approve", "reject"):
            p.add_argument("--note", default="")
    sub.add_parser("check", parents=[common]); sub.add_parser("board", parents=[common])
    args = ap.parse_args()
    vault = Path(args.vault) if args.vault else Path(__file__).resolve().parent.parent

    if args.cmd == "new":
        return cmd_new(args, vault)
    if args.cmd == "list":
        return cmd_list(args, vault)
    if args.cmd == "check":
        return cmd_check(vault)
    if args.cmd == "board":
        return cmd_board(vault)
    return cmd_transition(args.cmd, args, vault)


if __name__ == "__main__":
    sys.exit(main())
