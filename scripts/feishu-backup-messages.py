#!/usr/bin/env python3
# scripts/feishu-backup-messages.py
# 备份飞书聊天记录 → raw/private/feishu/messages/
#   单聊(p2p)→ messages/<对方>__<chatid8>.md
#   群聊(group)→ messages/groups/<群名>__<chatid8>.md
# 每个会话产出:.md(可读 transcript)+ .jsonl(全量原始消息)。
#
# 依赖:已授权 lark-cli(用户身份)。群聊需 scope:
#   im:chat:read(列群)+ im:message.group_msg:get_as_user(读群历史)
#   单聊需 im:message.p2p_msg:get_as_user。缺 scope 会在 --limit 冒烟时立刻报 need_user_authorization。
#
# 用法:
#   python3 scripts/feishu-backup-messages.py --types group --limit 3   # 群聊冒烟
#   python3 scripts/feishu-backup-messages.py --types group             # 全部群聊(增量)
#   python3 scripts/feishu-backup-messages.py --types p2p               # 单聊(原行为)
#   python3 scripts/feishu-backup-messages.py --types group,p2p         # 两者
#   python3 scripts/feishu-backup-messages.py --types group --force     # 强制全量重取
#
# 增量:对每个会话先探最新一条消息 id,与上次相同则跳过;不同则全量重取该会话。
# 说明:只导文本/内容字段,不下载图片/文件资源(资源提取交给 feishu-chat-digest.py 下游)。

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import larklib

VAULT = Path(__file__).resolve().parent.parent
FEISHU = larklib.feishu_root(VAULT)
OUT = FEISHU / "messages"
GROUP_OUT = OUT / "groups"
META = FEISHU / "_meta"
STATE_FILE = META / "messages-state.json"


def run(args, timeout=180):
    p = subprocess.run(larklib.lark_argv([*args, "--json"]), capture_output=True, text=True, timeout=timeout)
    out, err = p.stdout.strip(), p.stderr.strip()
    for blob in (out, err):  # 授权类错误 lark-cli 会把 JSON 打到 stderr
        if blob:
            try:
                return json.loads(blob)
            except json.JSONDecodeError:
                pass
    raise RuntimeError(f"非 JSON: {out[:150]} | {err[:150]}")


def call(args, what, retries=5):
    for a in range(retries):
        try:
            d = run(args)
        except Exception:
            if a == retries - 1:
                raise
            time.sleep(3 * (a + 1)); continue
        if d.get("ok"):
            return d
        err = d.get("error") or {}
        msg = json.dumps(err, ensure_ascii=False)
        sub, typ = err.get("subtype", ""), err.get("type", "")
        # 授权类错误不重试,直接给出可执行指引
        if sub in ("token_missing", "token_expired") or "authorization" in msg.lower():
            hint = err.get("hint") or "run: lark-cli auth login to re-authorize"
            raise RuntimeError(f"{what}: 需重新授权 → {hint}")
        # 瞬时错误:网络 / 超时 / 限流 → 退避重试(飞书 TLS 握手常间歇超时)
        transient = typ in ("network", "rate_limit") or sub in ("timeout", "rate_limited") or "rate" in msg.lower()
        if transient and a < retries - 1:
            time.sleep(3 * (a + 1)); continue
        raise RuntimeError(f"{what}: {msg}")
    raise RuntimeError(f"{what} 重试耗尽")


def fl(o, ks):
    if isinstance(o, dict):
        for k in ks:
            if isinstance(o.get(k), list):
                return o[k]
        for v in o.values():
            r = fl(v, ks)
            if r is not None:
                return r
    return None


def iter_chats(types, identity):
    """枚举指定类型(group/p2p)的会话。types 为逗号串;identity=user|bot。"""
    pt = None
    while True:
        args = ["im", "+chat-list", "--types", types, "--as", identity, "--page-size", "100"]
        if pt:
            args += ["--page-token", pt]
        data = call(args, "chat-list")["data"]
        for c in fl(data, ("items", "chats", "results")) or []:
            yield c
        pt = data.get("page_token")
        if not data.get("has_more") or not pt:
            break


def mode_of(chat, default):
    """判定会话类型:优先 chat_mode 字段,其次 p2p_target_id,最后回退请求的单一类型。"""
    cm = chat.get("chat_mode")
    if cm == "p2p":
        return "p2p"
    if cm in ("group", "topic"):
        return "group"
    if chat.get("p2p_target_id"):
        return "p2p"
    return default


def newest_message_id(chat_id, identity):
    d = call(["im", "+chat-messages-list", "--chat-id", chat_id, "--as", identity, "--order", "desc",
              "--page-size", "1", "--no-reactions"], f"probe {chat_id}")
    msgs = fl(d.get("data", {}), ("items", "messages", "results")) or []
    return msgs[0].get("message_id") if msgs else None


def fetch_all_messages(chat_id, identity):
    out = []
    pt = None
    while True:
        args = ["im", "+chat-messages-list", "--chat-id", chat_id, "--as", identity, "--order", "asc",
                "--page-size", "50", "--no-reactions"]
        if pt:
            args += ["--page-token", pt]
        data = call(args, f"messages {chat_id}")["data"]
        out += fl(data, ("items", "messages", "results")) or []
        pt = data.get("page_token")
        if not data.get("has_more") or not pt:
            break
        time.sleep(0.15)
    return out


def strip_tags(s):
    return re.sub(r"<[^>]+>", "", s or "").strip()


def safe(s, n=60):
    s = re.sub(r'[/\\:*?"<>|\n\r\t]+', "_", s or "").strip()
    s = re.sub(r"\s+", " ", s)
    return (s[:n].rstrip() or "untitled")


def render_md(chat, msgs, mode):
    """mode=p2p → 单聊框架(与历史产物一致);mode=group → 群聊框架。正文渲染一致。"""
    def esc(v):
        return json.dumps(str(v), ensure_ascii=False)
    times = [m.get("create_time") for m in msgs if m.get("create_time")]
    rng = esc((times[0] if times else "") + " ~ " + (times[-1] if times else ""))
    if mode == "group":
        name = strip_tags(chat.get("name") or chat["chat_id"])
        fm = ["---",
              f"title: {esc('群聊:' + name)}",
              "source: feishu-im-group",
              f"group: {esc(name)}",
              f"chat_id: {chat['chat_id']}",
              f"messages: {len(msgs)}",
              f"range: {rng}",
              f"fetched: {datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')}",
              "---", "", f"# 群聊:{name}", ""]
    else:
        name = strip_tags(chat.get("name") or chat.get("p2p_target_id") or chat["chat_id"])
        fm = ["---",
              f"title: {esc('与 ' + name + ' 的单聊')}",
              "source: feishu-im-p2p",
              f"peer: {esc(name)}",
              f"chat_id: {chat['chat_id']}",
              f"messages: {len(msgs)}",
              f"range: {rng}",
              f"fetched: {datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')}",
              "---", "", f"# 与 {name} 的单聊", ""]
    body = []
    for m in msgs:
        sender = (m.get("sender") or {}).get("name") or (m.get("sender") or {}).get("id", "?")
        t = m.get("create_time", "")
        mt = m.get("msg_type", "")
        content = m.get("content", "")
        if not isinstance(content, str):
            content = json.dumps(content, ensure_ascii=False)
        prefix = "" if mt == "text" else f"[{mt}] "
        if m.get("deleted"):
            prefix = "[已撤回] " + prefix
        body.append(f"**{sender}** · {t}\n{prefix}{content}\n")
    return "\n".join(fm) + "\n".join(body)


def load(p):
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def main():
    ap = argparse.ArgumentParser(description="备份飞书聊天记录(单聊 / 群聊)")
    ap.add_argument("--types", default="group",
                    help="会话类型:group | p2p | group,p2p(默认 group)")
    ap.add_argument("--identity", default="user", choices=["user", "bot"],
                    help="lark-cli 身份(群聊/单聊读历史都需 user,默认 user)")
    ap.add_argument("--chats", default="", help="只处理名字含这些子串的会话(逗号分隔;默认全部)")
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 个会话(冒烟测试)")
    ap.add_argument("--force", action="store_true", help="忽略增量,强制全量重取(不影响其它会话 state)")
    ap.add_argument("--sleep", type=float, default=0.2)
    args = ap.parse_args()

    types = ",".join(t.strip() for t in args.types.split(",") if t.strip())
    default_mode = types if types in ("group", "p2p") else "group"

    if not OUT.parent.exists():
        print(f"❌ {OUT.parent} 不存在(raw/private 是否已软链?)", file=sys.stderr); sys.exit(1)
    OUT.mkdir(parents=True, exist_ok=True)
    GROUP_OUT.mkdir(parents=True, exist_ok=True)
    META.mkdir(parents=True, exist_ok=True)
    # state 始终整体加载:--force 只跳过增量判断,绝不清空其它类型/会话的历史记录
    state = load(STATE_FILE)

    print(f"→ 枚举会话(types={types}, as={args.identity})...")
    try:
        chats = list(iter_chats(types, args.identity))
    except RuntimeError as e:
        print(f"❌ {e}", file=sys.stderr)
        print("   群聊需先授权:lark-cli auth login(勾选 im:chat:read + im:message.group_msg:get_as_user)", file=sys.stderr)
        sys.exit(2)
    print(f"  共 {len(chats)} 个会话")
    if args.chats:
        pats = [p.strip() for p in args.chats.split(",") if p.strip()]
        chats = [c for c in chats
                 if any(p in strip_tags(c.get("name") or c.get("p2p_target_id") or c["chat_id"]) for p in pats)]
        print(f"  --chats 过滤后 {len(chats)} 个(匹配 {pats})")
    if args.limit:
        chats = chats[: args.limit]

    done = skipped = failed = empty = 0
    for i, c in enumerate(chats, 1):
        cid = c["chat_id"]
        mode = mode_of(c, default_mode)
        name = strip_tags(c.get("name") or c.get("p2p_target_id") or cid)
        try:
            if not args.force and state.get(cid):
                nid = newest_message_id(cid, args.identity)
                if nid and nid == state[cid].get("last_id"):
                    skipped += 1
                    print(f"  [{i}/{len(chats)}] ⏭ 未变跳过 {name[:30]}", flush=True)
                    continue
            print(f"  [{i}/{len(chats)}] ↓ 抓取 [{mode}] {name[:30]} …", flush=True)
            msgs = fetch_all_messages(cid, args.identity)
        except Exception as e:
            failed += 1
            print(f"  [{i}/{len(chats)}] ✗ {name[:30]} — {str(e)[:100]}", file=sys.stderr, flush=True)
            continue

        if not msgs:
            empty += 1
            state[cid] = {"last_id": None, "count": 0, "name": name, "mode": mode}
            continue

        out_dir = GROUP_OUT if mode == "group" else OUT
        base = f"{safe(name)}__{cid[3:11]}"
        (out_dir / f"{base}.md").write_text(render_md(c, msgs, mode), encoding="utf-8")
        with open(out_dir / f"{base}.jsonl", "w", encoding="utf-8") as f:
            for m in msgs:
                f.write(json.dumps(m, ensure_ascii=False) + "\n")
        state[cid] = {"last_id": msgs[-1].get("message_id"), "count": len(msgs), "name": name, "mode": mode}
        STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        done += 1
        print(f"  [{i}/{len(chats)}] ✓ [{mode}] {name[:30]}  ({len(msgs)} 条)", flush=True)
        time.sleep(args.sleep)

    print(f"\n完成:写入 {done} · 跳过(未变){skipped} · 空会话 {empty} · 失败 {failed}")
    print(f"产物:单聊 {OUT} · 群聊 {GROUP_OUT}")


if __name__ == "__main__":
    main()
