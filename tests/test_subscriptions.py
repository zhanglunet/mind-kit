# tests/test_subscriptions.py — scripts/subscriptions.py 单元测试。
# 注意:本文件为纪律(#10)落地前的存量代码**事后补写**,非 RED-first;
# 以变异验证(注入 bug 变红→恢复变绿)替代,证据见提交记录。
import json
from datetime import date, timedelta

import subscriptions as S

TODAY = date.today()


# ---- add_months:月末对齐与跨年 ----

def test_add_months_basic():
    assert S.add_months(date(2026, 7, 7), 1) == date(2026, 8, 7)


def test_add_months_year_rollover():
    assert S.add_months(date(2026, 12, 15), 1) == date(2027, 1, 15)


def test_add_months_month_end_clamp():
    # 1月31日 + 1个月 → 2月最后一天(平年 28)
    assert S.add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)


def test_add_months_leap_year():
    # 闰年 2 月有 29 日
    assert S.add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)


# ---- next_renewal:顺推规则 ----

def test_next_renewal_rolls_forward():
    # anchor 在过去 → 顺推到 ≥ today 的下一期
    assert S.next_renewal(date(2026, 6, 24), "monthly", date(2026, 7, 21)) == date(2026, 7, 24)


def test_next_renewal_anchor_is_today():
    # anchor 即今天 → 今天就是续费日(0 天剩余),不再往后推
    assert S.next_renewal(TODAY, "monthly", TODAY) == TODAY


def test_next_renewal_yearly():
    assert S.next_renewal(date(2025, 8, 24), "yearly", date(2026, 7, 21)) == date(2026, 8, 24)


def test_next_renewal_quarterly_multi_hop():
    # 季付跨多期顺推
    assert S.next_renewal(date(2025, 1, 10), "quarterly", date(2026, 7, 21)) == date(2026, 10, 10)


# ---- load():数据装载、next 覆盖、异常周期 ----

def _sub(**kw):
    base = {"name": "X", "vendor": "", "category": "", "cost": None, "currency": "USD",
            "cycle": "monthly", "anchor": TODAY.isoformat(),
            "auto_renew": False, "url": "", "notes": ""}
    base.update(kw)
    return base


def _load_with(monkeypatch, tmp_path, subs):
    p = tmp_path / "subscriptions.json"
    p.write_text(json.dumps(subs), encoding="utf-8")
    monkeypatch.setattr(S, "DATA", str(p))
    return S.load()


def test_load_explicit_next_wins(monkeypatch, tmp_path):
    future = TODAY + timedelta(days=30)
    rows = _load_with(monkeypatch, tmp_path, [_sub(next=future.isoformat())])
    assert rows[0]["next"] == future
    assert rows[0]["left"] == 30


def test_load_expired_next_falls_back_to_anchor_cycle(monkeypatch, tmp_path):
    # next 已过期 → 回落 anchor+cycle 顺推
    anchor = TODAY - timedelta(days=10)
    expired = TODAY - timedelta(days=3)
    rows = _load_with(monkeypatch, tmp_path,
                      [_sub(anchor=anchor.isoformat(), next=expired.isoformat())])
    assert rows[0]["next"] == S.add_months(anchor, 1)


def test_load_unknown_cycle_skipped(monkeypatch, tmp_path, capsys):
    rows = _load_with(monkeypatch, tmp_path,
                      [_sub(name="好", cycle="monthly"), _sub(name="坏", cycle="weekly")])
    assert [r["name"] for r in rows] == ["好"]
    assert "未知 cycle" in capsys.readouterr().err


def test_load_sorted_by_next(monkeypatch, tmp_path):
    rows = _load_with(monkeypatch, tmp_path, [
        _sub(name="晚", next=(TODAY + timedelta(days=90)).isoformat()),
        _sub(name="早", next=(TODAY + timedelta(days=3)).isoformat()),
    ])
    assert [r["name"] for r in rows] == ["早", "晚"]


# ---- mark:临期分档(锁字面阈值 🔴≤5 / 🟡≤30,不引用常量本身——否则变异测不出来) ----

def test_thresholds_are_pinned():
    assert S.URGENT_DAYS == 5   # 2026-07-21 用户拍板:提前 5 天提醒
    assert S.WARN_DAYS == 30


def test_mark_urgent_at_threshold():
    assert S.mark(5) == "🔴"


def test_mark_warn_between_thresholds():
    assert S.mark(6) == "🟡"
    assert S.mark(30) == "🟡"


def test_mark_ok_beyond_warn():
    assert S.mark(31) == "⚪"
