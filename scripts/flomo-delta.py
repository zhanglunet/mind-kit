#!/usr/bin/env python3
# scripts/flomo-delta.py
# 比对两次 flomo 全量导出,提取新增笔记,生成 delta 文件供 sage-wiki 编译。
# flomo 每次导出是全量快照,此脚本确保只处理新内容,且不修改原始导出。
# 需要 Python 3.9+。
#
# 用法:python scripts/flomo-delta.py <新导出目录路径>
# 例:  python scripts/flomo-delta.py raw/flomo/2026-04-15
#
# 注意:必须传入 raw/flomo 下"某一次导出"的目录(不接受其它位置,防止把
# 整个 vault 误当笔记摄入)。笔记按行首 "- " 切分,"## " 视为结构标题;
# 若你的导出格式不同,请按实际格式微调(见 PRD §12 开放问题 2)。
import sys, os, re, json, hashlib
from pathlib import Path
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reportlib import atomic_write  # noqa: E402  复用同一份原子写入(单一实现)

VAULT = Path(__file__).parent.parent
FLOMO = (VAULT / "raw" / "flomo").resolve()
DELTA = FLOMO / "delta"
STATE = FLOMO / ".processed_hashes.json"

# 过滤掉去掉行首 "- " 标记后不足此字符数的碎片(空 bullet/纯分隔符);
# 阈值刻意很低:中文一句话短 memo 也是完整笔记,不应被丢弃。
MIN_NOTE_CHARS = 2


def split_notes(content: str) -> "tuple[list[str], int]":
    """按行首 "- " 切分笔记。返回 (笔记列表, 被跳过的块数)。

    flomo 导出中每条 memo 是 "- " 开头的块;"## " 行是日期/归档等结构标题,
    文件开头是标题、导出时间等元信息。标题块与头部元信息不算笔记:其中的
    导出时间戳每次都变,当作笔记会导致每次运行都重复输出一条"新笔记"。
    (若你的导出格式把笔记写成 "## " 开头,请调整此处;见 PRD §12 问题 2。)
    """
    notes, skipped = [], 0
    for block in re.split(r"\n(?=- |## )", content):
        block = block.strip()
        if not block:
            continue
        if not block.startswith("- "):
            skipped += 1  # 文件头部元信息 或 "## " 结构标题块(含其后续行)
            continue
        if len(block[2:].strip()) < MIN_NOTE_CHARS:
            skipped += 1  # 空 bullet / 纯分隔符碎片
            continue
        notes.append(block)
    return notes, skipped


def get_notes(folder: Path) -> "tuple[dict[str, str], int]":
    """从 flomo 导出文件夹读取所有笔记,返回 ({hash: content}, 跳过块数)。

    编码策略:严格 UTF-8。无法解码的文件跳过并醒目告警(绝不写入乱码、
    绝不静默丢字);被跳过文件的笔记未记入指纹,转码修复后重跑会自动补上。
    """
    files = sorted(folder.rglob("*.md"))
    if not files:
        sys.exit(f"错误:目录中没有找到任何 .md 文件:{folder}\n"
                 f"请确认传入的是 flomo 导出目录(含 Markdown 文件)。")
    notes, total_skipped, bad_files = {}, 0, []
    for f in files:
        try:
            content = f.read_bytes().decode("utf-8")
        except UnicodeDecodeError as e:
            bad_files.append((f, e))
            continue
        blocks, skipped = split_notes(content)
        total_skipped += skipped
        for block in blocks:
            h = hashlib.md5(block.encode("utf-8")).hexdigest()
            notes[h] = block
    if bad_files:
        print("⚠ 警告:以下文件不是 UTF-8 编码,本次已跳过(内容未进入 delta):")
        for f, e in bad_files:
            print(f"  - {f}({e.reason},字节偏移 {e.start})")
        print("  请转为 UTF-8(如 iconv -f GBK -t UTF-8)后重跑,笔记会自动补上。")
        if len(bad_files) == len(files):
            sys.exit("错误:所有文件均无法以 UTF-8 解码,已中止。")
    return notes, total_skipped


def load_state() -> "set[str]":
    """加载已处理 hash 集合;状态文件损坏时给出明确指引而非 traceback。"""
    if not STATE.exists():
        return set()
    try:
        return set(json.loads(STATE.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError) as e:
        sys.exit(f"错误:状态文件损坏或不可读:{STATE}\n"
                 f"原因:{e}\n"
                 f"处理方式:若该文件曾提交进 git,请用 git 历史恢复;\n"
                 f"否则请勿直接删除——删除后下次运行会把全部历史笔记当作新增,\n"
                 f"造成 sage-wiki 大规模重复编译。可先备份损坏文件再人工修复 JSON。")


def main():
    if len(sys.argv) < 2:
        sys.exit("用法:python scripts/flomo-delta.py <新导出目录路径>")
    new_folder = Path(sys.argv[1]).resolve()
    if not new_folder.is_dir():
        sys.exit(f"错误:路径不存在或不是目录:{new_folder}")
    # 正向校验:输入必须是 raw/flomo 下的导出目录(且不是 delta 输出目录)。
    # 这一条同时挡住 raw/flomo 根目录、vault 根、raw/、_wiki/ 等所有误传,
    # 避免把整个库的 .md 误当笔记摄入并永久污染指纹状态。
    if new_folder == FLOMO or not new_folder.is_relative_to(FLOMO):
        sys.exit("错误:请传入 raw/flomo 下某一次导出的具体目录"
                 f"(如 raw/flomo/2026-04-15);收到:{new_folder}")
    if new_folder == DELTA or new_folder.is_relative_to(DELTA):
        sys.exit("错误:raw/flomo/delta 是本脚本的输出目录,不能作为输入。")

    processed = load_state()
    all_notes, skipped = get_notes(new_folder)
    new_notes = {h: c for h, c in all_notes.items() if h not in processed}
    if skipped:
        print(f"(已跳过 {skipped} 个非笔记块:文件头部元信息/结构标题/空碎片)")
    if not new_notes:
        print("没有新增笔记。")
        return

    # 生成 delta 文件:文件名带时间到秒,同日多次运行互不覆盖
    DELTA.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    stamp = now.strftime("%Y-%m-%d-%H%M%S")
    delta_file = DELTA / f"delta-{stamp}.md"
    n = 1
    while delta_file.exists():  # 同一秒内处理多个导出目录时仍不覆盖
        delta_file = DELTA / f"delta-{stamp}-{n}.md"
        n += 1
    lines = [
        "---",
        f"title: flomo delta {date_str}",
        "source: flomo-export",
        f"date: {date_str}",
        "tags: [flomo, personal]",
        "type: note",
        "---",
        "",
        f"# flomo 增量笔记 {date_str}",
        "",
        f"共 {len(new_notes)} 条新笔记。",
        "",
    ]
    for content in new_notes.values():
        lines.append(content)
        lines.append("")
        lines.append("---")
        lines.append("")
    atomic_write(delta_file, "\n".join(lines))
    print(f"已生成 delta 文件:{delta_file}")
    print(f"包含 {len(new_notes)} 条新笔记")

    # 更新已处理 hash 记录(原子写入;顺序在 delta 之后,崩溃最多重复、不会丢失)
    processed.update(new_notes.keys())
    atomic_write(STATE, json.dumps(sorted(processed)))

    # 提示后续步骤
    print("\n下一步:")
    print("1. sage-wiki compile （自动编译进 _wiki/）")
    print("2. 在 Claudian 中运行六类素材提取,处理 raw/flomo/delta/ 的新内容")


if __name__ == "__main__":
    main()
