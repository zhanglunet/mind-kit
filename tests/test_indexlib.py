"""indexlib.input_fingerprint 的行为测试(P0-3a,借鉴同类项目的索引指纹自失效)。
契约:对输入文件按相对路径排序,逐个把 `相对路径+\\0+内容字节+\\0` 喂入 sha256,
返回 {"fingerprint": hex, "file_count": n}。任何内容/路径变化都必须改变指纹;列出顺序无关。
"""
from pathlib import Path

import indexlib


def _mk(tmp_path: Path, name: str, text: str) -> Path:
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def test_same_inputs_same_fingerprint(tmp_path):
    a = _mk(tmp_path, "a.md", "内容A")
    b = _mk(tmp_path, "sub/b.md", "content B")
    f1 = indexlib.input_fingerprint([a, b], base=tmp_path)
    f2 = indexlib.input_fingerprint([a, b], base=tmp_path)
    assert f1 == f2
    assert f1["file_count"] == 2
    assert len(f1["fingerprint"]) == 64  # sha256 hex


def test_order_independent(tmp_path):
    a = _mk(tmp_path, "a.md", "x")
    b = _mk(tmp_path, "b.md", "y")
    assert (indexlib.input_fingerprint([a, b], base=tmp_path)
            == indexlib.input_fingerprint([b, a], base=tmp_path))


def test_content_change_changes_fingerprint(tmp_path):
    a = _mk(tmp_path, "a.md", "v1")
    before = indexlib.input_fingerprint([a], base=tmp_path)
    a.write_text("v2", encoding="utf-8")
    after = indexlib.input_fingerprint([a], base=tmp_path)
    assert before["fingerprint"] != after["fingerprint"]


def test_rename_changes_fingerprint(tmp_path):
    a = _mk(tmp_path, "a.md", "同样内容")
    fa = indexlib.input_fingerprint([a], base=tmp_path)
    b = _mk(tmp_path, "b.md", "同样内容")
    fb = indexlib.input_fingerprint([b], base=tmp_path)
    assert fa["fingerprint"] != fb["fingerprint"]  # 路径参与哈希,防"换名不换指纹"


def test_empty_input_stable(tmp_path):
    f = indexlib.input_fingerprint([], base=tmp_path)
    assert f["file_count"] == 0
    assert len(f["fingerprint"]) == 64


def test_fingerprint_skips_file_vanished_mid_scan(tmp_path):
    # 评审确认问题:glob 与读取之间文件被删(如 compile 重写 vault)→ 不得抛异常;
    # 消失的文件不计入,下一轮扫描指纹自然变化触发刷新
    a = _mk(tmp_path, "a.md", "在")
    b = tmp_path / "b.md"   # 列表里有、盘上没有
    f = indexlib.input_fingerprint([a, b], base=tmp_path)
    assert f["file_count"] == 1


def test_fingerprint_works_through_symlinked_dirs(tmp_path):
    # 生产布局:mind/_wiki 是指向 ../mind-vault/_wiki 的软链。
    # 指纹必须按"字面路径"(base 下的软链路径)计算,不能 resolve 穿透软链——
    # 否则 relative_to(base) 直接抛 ValueError(文件真身不在 base 下)。
    vault_real = tmp_path / "mind-vault"
    (vault_real / "_wiki" / "concepts").mkdir(parents=True)
    (vault_real / "_wiki" / "concepts" / "页.md").write_text("内容", encoding="utf-8")
    mind = tmp_path / "mind"
    mind.mkdir()
    (mind / "_wiki").symlink_to("../mind-vault/_wiki")

    files = indexlib.browse_inputs(mind)
    assert [p.name for p in files] == ["页.md"]
    f = indexlib.input_fingerprint(files, base=mind)   # 不得抛 ValueError
    assert f["file_count"] == 1
    # 内容变化仍能被察觉(经软链)
    (vault_real / "_wiki" / "concepts" / "页.md").write_text("改了", encoding="utf-8")
    f2 = indexlib.input_fingerprint(indexlib.browse_inputs(mind), base=mind)
    assert f2["fingerprint"] != f["fingerprint"]


def test_browse_inputs_skips_missing_dirs(tmp_path):
    # 容器/CI 里 vault 目录可能不存在:browse_inputs 必须优雅返回空列表而非崩溃
    assert indexlib.browse_inputs(tmp_path) == []
    _mk(tmp_path, "_wiki/concepts/概念页.md", "x")
    _mk(tmp_path, "material/quotes/金句.md", "y")
    got = [p.name for p in indexlib.browse_inputs(tmp_path)]
    assert "概念页.md" in got and "金句.md" in got


def test_browse_inputs_only_six_material_subdirs(tmp_path):
    # 评审确认问题:指纹面须与浏览站实际输入面一致——material 只认六类子目录,
    # 其它子目录(如 inbox)的变化不参与指纹,否则会假报 browse_stale
    _mk(tmp_path, "material/quotes/a.md", "在渲染面内")
    _mk(tmp_path, "material/inbox/b.md", "不在渲染面内")
    got = [str(p) for p in indexlib.browse_inputs(tmp_path)]
    assert any("quotes" in p for p in got)
    assert not any("inbox" in p for p in got)
