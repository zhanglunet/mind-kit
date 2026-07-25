# scripts/indexlib.py
# 索引/构建产物的输入指纹(P0-3a,机制借鉴同类项目实践:"索引输入指纹自失效",自行实现)。
# 用途:build-wiki-site.py 构建浏览站时记录输入指纹;brain-server.py /api/ping 按需重算比对,
# 发现浏览站落后于 vault("结构可解析 ≠ 索引新鲜")。
import hashlib
import os
from pathlib import Path

MANIFEST_SCHEMA = "browse-manifest-1"

# material 六类子目录(与 build-wiki-site.py 的 MAT_LABELS 对齐;两处名单不一致会假报 stale)
MAT_SUBDIRS = ("quotes", "stories", "references", "cases", "frameworks", "data")


def input_fingerprint(files, base) -> dict:
    """对输入文件集合计算单一 sha256 指纹。
    按相对路径排序后,逐个把 `相对路径 + \\0 + 内容字节 + \\0` 喂入同一哈希:
    内容变化、增删文件、重命名(路径参与哈希)都会改变指纹;列出顺序无关。
    相对路径按**字面路径**计算(os.path.relpath,不 resolve 穿透软链)——
    生产布局里 _wiki/material 是指向 mind-vault 的软链,穿透后真身不在 base 下,
    resolve+relative_to 会抛 ValueError(tests/test_indexlib.py 有回归)。
    返回 {"fingerprint": hex64, "file_count": n}。
    """
    base = Path(base)
    h = hashlib.sha256()
    entries = sorted((os.path.relpath(str(f), str(base)), Path(f)) for f in files)
    count = 0
    for rel, p in entries:
        try:
            data = p.read_bytes()
        except OSError:
            continue   # 列举与读取之间文件被删(如 compile 重写 vault):跳过;下轮扫描指纹自然变化
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(data)
        h.update(b"\0")
        count += 1
    return {"fingerprint": h.hexdigest(), "file_count": count}


def browse_inputs(vault) -> "list[Path]":
    """浏览站(build-wiki-site.py)的输入文件面:_wiki/{concepts,summaries,outputs}/*.md
    + material 六类子目录的 *.md,与其 collect() 精确对齐(其它 material 子目录不参与
    渲染,也不参与指纹,避免假 stale)。目录缺失(容器/CI 无 vault 软链)时优雅跳过。"""
    vault = Path(vault)
    out = []
    for sub in ("concepts", "summaries", "outputs"):
        d = vault / "_wiki" / sub
        if d.is_dir():
            out += sorted(d.glob("*.md"))
    for sub in MAT_SUBDIRS:
        d = vault / "material" / sub
        if d.is_dir():
            out += sorted(d.glob("*.md"))
    return out
