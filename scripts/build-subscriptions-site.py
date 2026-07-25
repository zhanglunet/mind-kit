#!/usr/bin/env python3
# scripts/build-subscriptions-site.py — 订阅台账页面生成器。
# 读 mind-vault/subscriptions.json(数据源,手工维护),渲染本地私密页
# browse/subscriptions/index.html(自包含,file:// 直开;browse/ 整目录 gitignore)。
# 临期规则与 CLI 一致:🔴 ≤5 天 / 🟡 ≤30 天;费用折算月支出(按币种分组)。
#
# 用法:python3 scripts/build-subscriptions-site.py(之后跑 build-portal.py 刷新门户卡片)
# 每日 cron 会自动重建(见 subscriptions.py 头部),改了 json 也可手动重跑。

import html
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import subscriptions as S  # noqa: E402

VAULT = Path(__file__).resolve().parent.parent
OUT = VAULT / "browse" / "subscriptions"

CSS = """
:root{--ink:#1f2328;--sub:#6a737d;--line:#e1e4e8;--bg:#f6f8fa;--brand:#2b6cb0;--red:#d73a49;--amber:#b08800}
*{box-sizing:border-box}body{margin:0;font:15px/1.7 -apple-system,"PingFang SC","Microsoft YaHei",sans-serif;color:var(--ink);background:#fff}
.wrap{max-width:920px;margin:0 auto;padding:24px 20px 80px}
h1{font-size:24px;margin:8px 0 4px}
.sub{color:var(--sub);font-size:13px;margin-bottom:20px}
.stats{display:flex;gap:14px;flex-wrap:wrap;margin:16px 0 24px}
.stat{background:var(--bg);border:1px solid var(--line);border-radius:10px;padding:10px 18px}
.stat b{font-size:20px;color:var(--brand)}
.stat.warn b{color:var(--amber)}.stat.urgent b{color:var(--red)}
table{border-collapse:collapse;width:100%;font-size:14px;margin:12px 0}
td,th{border:1px solid var(--line);padding:8px 12px;vertical-align:top;text-align:left}
thead th{background:var(--bg)}
tr.urgent td{background:#fff5f5}tr.warn td{background:#fffdf2}
.days{font-weight:600;white-space:nowrap}
tr.urgent .days{color:var(--red)}tr.warn .days{color:var(--amber)}
.tag{display:inline-block;border:1px solid var(--line);border-radius:12px;padding:0 8px;font-size:12px;color:var(--sub);margin-right:4px}
.tag.auto{border-color:#2b6cb0;color:var(--brand)}
a{color:var(--brand);text-decoration:none}a:hover{text-decoration:underline}
.mut{color:var(--sub);font-size:13px}
footer{margin-top:40px;color:var(--sub);font-size:12px;border-top:1px solid var(--line);padding-top:12px}
"""


def fmt_cost(r):
    if r.get("cost") is None:
        return '<span class=mut>—</span>'
    return f"{r['cost']:g} {r['currency']}/{CYCLE_UNIT[r['cycle']]}"


CYCLE_UNIT = {"monthly": "月", "quarterly": "季", "semiannual": "半年", "yearly": "年"}
FX_TO_CNY = {"CNY": 1.0, "USD": 7.2}  # 固定折算汇率(约值,行情变了改这里)


def monthly_equiv(rows):
    """折算月支出,按币种分组;cost 为空的不计。"""
    totals = defaultdict(float)
    for r in rows:
        if r.get("cost") is None:
            continue
        totals[r["currency"]] += r["cost"] / S.CYCLE_MONTHS[r["cycle"]]
    return totals


def render(rows):
    urgent = [r for r in rows if r["left"] <= S.URGENT_DAYS]
    warn = [r for r in rows if S.URGENT_DAYS < r["left"] <= S.WARN_DAYS]
    mtot = monthly_equiv(rows)
    mtot_s = " + ".join(f"{v:.2f} {k}" for k, v in sorted(mtot.items())) or "—"
    cny = sum(v * FX_TO_CNY.get(k, 0) for k, v in mtot.items())
    unknown = sorted(set(mtot) - set(FX_TO_CNY))
    cny_s = (f"≈ ¥{cny:,.0f}/月" + ("(含未折算币种:" + "/".join(unknown) + ")" if unknown
             else f"(USD 按 {FX_TO_CNY['USD']:g})"))

    trs = []
    for r in rows:
        cls = "urgent" if r["left"] <= S.URGENT_DAYS else "warn" if r["left"] <= S.WARN_DAYS else ""
        name = html.escape(r["name"])
        tags = [f'<span class=tag>{html.escape(r["category"])}</span>'] if r.get("category") else []
        if r.get("auto_renew"):
            tags.append('<span class=tag auto>自动续费</span>')
        notes = f'<div class=mut>{html.escape(r["notes"])}</div>' if r.get("notes") else ""
        vendor = html.escape(r.get("vendor") or "")
        trs.append(f"""<tr class="{cls}"><td>{name}<div class=mut>{vendor}</div></td>
<td>{S.CYCLE_CN[r['cycle']]}</td><td>{fmt_cost(r)}</td>
<td>{r['next'].isoformat()}</td><td class=days>{r['left']} 天</td>
<td>{''.join(tags)}{notes}</td></tr>""")

    page = f"""<!doctype html><html lang=zh><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>订阅台账 · 第二大脑</title><style>{CSS}</style>
<div class=wrap>
<p class=back><a href="../index.html">← 返回个人入口</a></p>
<h1>💳 订阅台账</h1>
<p class=sub>数字产品订阅一览,按下次续费日排序;🔴 ≤{S.URGENT_DAYS} 天到期 / 🟡 ≤{S.WARN_DAYS} 天。
生成于 {datetime.now():%Y-%m-%d %H:%M} · 重建:python3 scripts/build-subscriptions-site.py</p>
<div class=stats>
<div class=stat><b>{len(rows)}</b> 项订阅</div>
<div class="stat{' urgent' if urgent else ''}"><b>{len(urgent)}</b> 项 ≤{S.URGENT_DAYS} 天到期</div>
<div class="stat{' warn' if warn else ''}"><b>{len(warn)}</b> 项 ≤{S.WARN_DAYS} 天</div>
<div class=stat><b style="font-size:15px">{cny_s}</b><br><span class=mut>{mtot_s}</span><br>折算月支出</div>
</div>
<table><thead><tr><th>名称</th><th>周期</th><th>费用</th><th>下次续费</th><th>剩余</th><th>备注</th></tr></thead>
<tbody>{''.join(trs)}</tbody></table>
<footer>数据源:mind-vault/subscriptions.json(手工维护,anchor = 上次扣费日,脚本按周期顺推;勿放卡号等敏感信息)。
每日 cron 跑 subscriptions.py --notify,≤{S.URGENT_DAYS} 天到期弹系统通知并重建本页。</footer>
</div>"""
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "index.html").write_text(page, encoding="utf-8")
    print(f"✅ 订阅台账已生成:{OUT / 'index.html'}({len(rows)} 项,临期 {len(urgent)+len(warn)})")


def main():
    render(S.load())


if __name__ == "__main__":
    main()
