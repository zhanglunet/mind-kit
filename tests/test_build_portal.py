"""build-portal.py 的行为测试:门户 hero 含「全量更新」按钮并接线到本地服务端点。
连字符文件名用 importlib 按路径装载(与 test_brain_server 同法)。
"""
import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _load():
    spec = importlib.util.spec_from_file_location("build_portal", REPO / "scripts" / "build-portal.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_hero_has_update_button_wired_to_endpoints(tmp_path, monkeypatch):
    m = _load()
    monkeypatch.setattr(m, "VAULT", tmp_path)          # 空库:query_stats/recent_decisions 走空路径
    monkeypatch.setattr(m, "OUT", tmp_path / "browse")
    hero = m.build_hero()
    assert "id=upd" in hero, "hero 应有全量更新按钮"
    assert "runUpdate" in hero
    assert "/api/update-all" in hero, "按钮须 POST 触发端点"
    assert "/api/update-status" in hero, "须轮询状态端点回显进度"


def test_main_writes_portal_with_update_button(tmp_path, monkeypatch):
    m = _load()
    monkeypatch.setattr(m, "VAULT", tmp_path)
    out = tmp_path / "browse"
    monkeypatch.setattr(m, "OUT", out)
    m.main()
    page = (out / "index.html").read_text(encoding="utf-8")
    assert "🔄 全量更新" in page and "id=upd" in page


def test_update_button_disabled_until_ping(tmp_path, monkeypatch):
    # 未探到本地服务前按钮应 disabled(ping 成功才点亮),避免离线时点了没反应
    m = _load()
    monkeypatch.setattr(m, "VAULT", tmp_path)
    monkeypatch.setattr(m, "OUT", tmp_path / "browse")
    hero = m.build_hero()
    assert "id=upd" in hero
    upd = hero[hero.index("id=upd"):hero.index("id=upd") + 120]
    assert "disabled" in upd, "全量更新按钮初始应禁用,待 ping 点亮"
