# tests/test_build_subscriptions_site.py — scripts/build-subscriptions-site.py 单元测试。
# 文件名带连字符不能直接 import,用 importlib 按路径装载。
# 同为存量代码事后补写,证据见提交记录。
import importlib.util
from datetime import date, timedelta
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "build_subscriptions_site",
    Path(__file__).resolve().parent.parent / "scripts" / "build-subscriptions-site.py")
B = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(B)

TODAY = date.today()


def _row(**kw):
    base = {"name": "Claude Code", "vendor": "Anthropic", "category": "AI 工具",
            "cost": 249.99, "currency": "USD", "cycle": "monthly",
            "next": TODAY + timedelta(days=16), "left": 16,
            "auto_renew": True, "url": "https://claude.ai", "notes": ""}
    base.update(kw)
    return base


# ---- monthly_equiv:折算月支出 ----

def test_monthly_equiv_cycle_division():
    rows = [_row(cost=120.0, cycle="yearly"),      # 年付 120 → 10/月
            _row(cost=30.0, cycle="quarterly")]    # 季付 30  → 10/月
    totals = B.monthly_equiv(rows)
    assert totals["USD"] == pytest.approx(20.0)


def test_monthly_equiv_groups_by_currency_and_skips_null():
    rows = [_row(cost=249.99, currency="USD"),
            _row(cost=169, currency="CNY"),
            _row(name="无费用", cost=None)]
    totals = B.monthly_equiv(rows)
    assert totals["USD"] == pytest.approx(249.99)
    assert totals["CNY"] == pytest.approx(169)
    assert len(totals) == 2


# ---- render:页面渲染(写到 tmp,不碰真实 browse/) ----

def _render(tmp_path, monkeypatch, rows):
    monkeypatch.setattr(B, "OUT", tmp_path)
    B.render(rows)
    return (tmp_path / "index.html").read_text(encoding="utf-8")


def test_render_cny_total_with_fx(tmp_path, monkeypatch):
    # 月付 72 USD → 折 ¥518(72×7.2=518.4)
    html = _render(tmp_path, monkeypatch, [_row(cost=72.0)])
    assert "≈ ¥518/月" in html
    assert "72.00 USD" in html  # 原始币种明细仍列出


def test_render_no_product_links(tmp_path, monkeypatch):
    # 2026-07-21 用户要求:名称不渲染产品外链
    html = _render(tmp_path, monkeypatch, [_row(url="https://claude.ai")])
    assert "↗" not in html
    assert '<a href="https://claude.ai"' not in html
    assert "Claude Code" in html
    assert "Anthropic" in html


def test_render_urgent_and_warn_rows(tmp_path, monkeypatch):
    rows = [_row(name="急", left=5, next=TODAY + timedelta(days=5)),
            _row(name="缓", left=20, next=TODAY + timedelta(days=20))]
    html = _render(tmp_path, monkeypatch, rows)
    assert 'class="urgent"' in html
    assert 'class="warn"' in html
    assert "🔴 ≤5 天到期" in html


def test_render_shows_fx_note(tmp_path, monkeypatch):
    html = _render(tmp_path, monkeypatch, [_row()])
    assert f"USD 按 {B.FX_TO_CNY['USD']:g}" in html
