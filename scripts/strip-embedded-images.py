#!/usr/bin/env python3
# scripts/strip-embedded-images.py — 剥离 md 里内嵌的 base64 图片(某些导出常见的"图片炸弹")。
# 背景:某些平台批量导出的 md 会把截图整个 base64 内嵌(单行可达 MB 级),把 16KB 的正文撑成 16MB,
# 既骗高按字数的分档判断,也没法喂给 sage-wiki compile(120s 超时)。
# 本脚本**只读源文件、写净化副本**,不修改原件(冷存原件保留全部图片)。
#
# 用法:
#   python3 scripts/strip-embedded-images.py <src.md> <dst.md>   # 净化到目标文件
#   python3 scripts/strip-embedded-images.py <src.md>            # 打印到 stdout(预览)
#
# 与 localize-images.py 的分工:那个管"外链图下载到本地";这个管"内嵌 base64 剥离"。

import re
import sys
from pathlib import Path

# ![alt](data:image/...;base64,....) —— markdown 内嵌图
MD_IMG = re.compile(r'!\[([^\]]*)\]\(\s*data:image/[^)]+\)')
# <img src="data:image/...;base64,...."> —— HTML 内嵌图(某些导出偶见)
HTML_IMG = re.compile(r'<img[^>]+src\s*=\s*["\']data:image/[^"\']+["\'][^>]*>', re.I)
# 兜底:裸奔的超长 base64 data-URI(未包在图片语法里)
BARE_URI = re.compile(r'data:image/[a-z+]+;base64,[A-Za-z0-9+/=\s]{200,}')

PLACEHOLDER = '【图:{alt}(base64 已剥离,原件见冷存)】'


def strip_images(text):
    n = 0

    def md_repl(m):
        nonlocal n
        n += 1
        alt = m.group(1).strip() or '图片'
        return PLACEHOLDER.format(alt=alt)

    def plain_repl(m):
        nonlocal n
        n += 1
        return PLACEHOLDER.format(alt='图片')

    text = MD_IMG.sub(md_repl, text)
    text = HTML_IMG.sub(plain_repl, text)
    text = BARE_URI.sub(plain_repl, text)
    return text, n


def main():
    if len(sys.argv) < 2 or len(sys.argv) > 3:
        sys.exit('用法: strip-embedded-images.py <src.md> [dst.md]')
    src = Path(sys.argv[1])
    if not src.is_file():
        sys.exit(f'不是文件: {src}')

    raw = src.read_bytes()
    for enc in ('utf-8', 'gbk'):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        sys.exit(f'{src} 既非 UTF-8 也非 GBK,无法解码')

    cleaned, n = strip_images(text)

    if len(sys.argv) == 3:
        dst = Path(sys.argv[2])
        dst.write_text(cleaned, encoding='utf-8')
        print(f'✅ 剥离 {n} 张内嵌图: {len(raw):,} B → {len(cleaned.encode("utf-8")):,} B → {dst}')
    else:
        sys.stdout.write(cleaned)
        print(f'\n--- 剥离 {n} 张内嵌图: {len(raw):,} B → {len(cleaned.encode("utf-8")):,} B (stdout 预览) ---', file=sys.stderr)


if __name__ == '__main__':
    main()
