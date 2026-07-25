#!/usr/bin/env python3
# scripts/build-portal.py — 生成本地私密「个人信息入口」→ browse/index.html。
# 一个统一入口,汇聚:知识库 Wiki(browse/wiki/)、订阅台账(browse/subscriptions/)、产品文档。
# 公私分明:browse/ 整目录 gitignore(私密,本地 file:// 打开);公开文档在 site/,
#          门户按 ../site/ 相对链接过去。绝不随公开站部署。
# 用法:python3 scripts/build-portal.py(建议在 build-wiki-site.py 之后跑)

import html
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

VAULT = Path(__file__).resolve().parent.parent
OUT = VAULT / "browse"          # 私密门户输出目录(整目录 gitignore)


def n(*globs):
    c = 0
    for base, pat in globs:
        p = VAULT / base
        if p.exists():
            c += sum(1 for _ in p.glob(pat))
    return c


def card(icon, title, desc, links, count=""):
    ls = " · ".join(f'<a href="{href}">{html.escape(t)}</a>' for t, href in links)
    cnt = f'<span class=cnt>{count}</span>' if count else ""
    return (f'<div class=card><div class=ct><span class=ic>{icon}</span>'
            f'<span class=tt>{html.escape(title)}</span>{cnt}</div>'
            f'<p class=ds>{html.escape(desc)}</p><div class=lk>{ls}</div></div>')


# ---- 调用(query)环节:让"问库"成为首页第一动作 ----------------------------
# 北极星 = 调用率。静态页做不了真·在线查询(sage-wiki serve 是 MCP 协议非 HTTP),
# 所以设计为「一键装弹 + 记分反馈」:输入问题→复制成 Claude / 引擎调用指令;
# 记分牌在构建时从 _wiki/log.md 的 `## [日期] query ｜ …` 条目算出(cron 每日刷新)。

DIM_TPL = {  # 与 _wiki/outputs/五维决策看板.md 的查询模板保持一致
    "市场与竞争": "从『市场与竞争』维度分析 <议题>:现在谁在做?竞争格局与差异化?最近的融资/政策/市场信号?时机如何?",
    "技术判断": "从『技术判断』维度分析 <议题>:核心技术路线与架构?可行性与工程陷阱?技术护城河与被颠覆风险?",
    "产品与用户": "从『产品与用户』维度分析 <议题>:真实需求与场景?用户价值主张?体验与采用门槛?",
    "人与组织": "从『人与组织』维度分析 <议题>:关键的人与团队?组织/治理结构?协作与人才瓶颈?",
    "框架与心智模型": "从『框架与心智模型』维度分析 <议题>:适用哪些思维框架/心智模型?第一性原理如何拆解?",
}

WEEK_TARGET = 2  # 每周调用目标(1 决策查询 + 1 写作取料)


def query_stats():
    """从 _wiki/log.md 数 query 调用:(全部条目[(日期,标题)…], 本周次数)。"""
    log = VAULT / "_wiki" / "log.md"
    entries = []
    if log.exists():
        for m in re.finditer(r'^## \[(\d{4}-\d{2}-\d{2})\] query ｜ (.+)$',
                             log.read_text(encoding="utf-8"), re.M):
            entries.append((m.group(1), m.group(2).strip()))
    today = datetime.now().date()
    monday = today - timedelta(days=today.weekday())
    week = 0
    for d, _ in entries:
        try:
            if monday <= datetime.strptime(d, "%Y-%m-%d").date() <= today:
                week += 1
        except ValueError:
            continue
    return entries, week


def recent_decisions(limit=4):
    """扫 _wiki/outputs 带 dimension 的页(五维决策产出),按 date 降序;能链 browse/wiki 就链。"""
    rows = []
    for p in (VAULT / "_wiki" / "outputs").glob("*.md"):
        try:
            head = p.read_text(encoding="utf-8")[:800]
        except OSError:
            continue
        if not head.startswith("---"):
            continue
        dm = re.search(r'^dimension:\s*\[(.+?)\]', head, re.M)
        if not dm or "看板" in p.stem:
            continue
        dt = re.search(r'^date:\s*(\S+)', head, re.M)
        ti = re.search(r'^title:\s*(.+)$', head, re.M)
        title = ti.group(1).strip() if ti else p.stem
        href = f"wiki/{p.stem}.html" if (OUT / "wiki" / f"{p.stem}.html").exists() else None
        rows.append((dt.group(1) if dt else "", title, href, dm.group(1)))
    rows.sort(key=lambda r: r[0], reverse=True)
    return rows[:limit]


HERO_JS = """<script>
const T=%TPL%;
var API=(location.protocol==='file:')?'http://127.0.0.1:8788':'';
function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}
function render(t){return esc(t).replace(/\\[\\[([^\\]]+)\\]\\]/g,function(_,p){
return '<a href="wiki/'+encodeURIComponent(p)+'.html">'+p+'</a>'})}
function ping(){fetch(API+'/api/ping').then(function(r){return r.json()}).then(function(j){
if(j.ok){var b=document.getElementById('goq');b.disabled=false;b.title='';
var u=document.getElementById('upd');if(u){u.disabled=false;u.title=''}
document.getElementById('srv').textContent=(j.browse_stale===true)?
'⚠️ 浏览站已落后于知识库,重跑 python3 scripts/build-wiki-site.py 刷新':''}}).catch(function(){
document.getElementById('srv').textContent='(在线查询/全量更新需本地服务:python3 scripts/brain-server.py)'})}
function runQuery(b){var q=val();if(!q){document.getElementById('q').focus();return}
var a=document.getElementById('ans');a.style.display='block';
var t0=Date.now();var tick=setInterval(function(){
a.innerHTML='⏳ 引擎综合中… '+Math.round((Date.now()-t0)/1000)+'s(通常 30 秒–2 分钟;产物会存 under_review 并自动记账)'},1000);
a.innerHTML='⏳ 引擎综合中…';b.disabled=true;
fetch(API+'/api/query',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({q:q})})
.then(function(r){return r.json()})
.then(function(j){clearInterval(tick);b.disabled=false;
if(j.ok&&j.hit===false){a.innerHTML='<div class=anst>🫥 库内无命中(已试过关键词化重查)。试试更短的关键词,或换「🤖 复制给 Claude」走综合查询。</div>'}
else if(j.ok){var fb=j.fallback?' · 已自动改写为关键词检索':'';
a.innerHTML='<div class=anst>✅ '+Math.round((Date.now()-t0)/1000)+'s'+fb+' · 产物已存 '+esc(j.saved)+' · 调用已记账</div><div class=ansb>'+render(j.answer)+'</div>'}
else{a.innerHTML='<div class=anst>❌ '+esc(j.error||'查询失败')+'</div><div class=ansb>'+esc(j.detail||'')+'</div>'}})
.catch(function(e){clearInterval(tick);b.disabled=false;
a.innerHTML='<div class=anst>❌ 连接失败:'+esc(String(e))+'</div>'})}
ping();
function chip(d){var q=document.getElementById('q');q.value=T[d];q.focus();
var i=q.value.indexOf('<议题>');if(i>=0)q.setSelectionRange(i,i+4);}
function val(){return document.getElementById('q').value.trim()}
function flash(b){var o=b.textContent;b.textContent='✅ 已复制';setTimeout(function(){b.textContent=o},1200)}
function cp(t,b){var f=function(){var a=document.createElement('textarea');a.value=t;
document.body.appendChild(a);a.select();try{document.execCommand('copy')}catch(e){}a.remove();flash(b)};
if(navigator.clipboard){navigator.clipboard.writeText(t).then(function(){flash(b)},f)}else f()}
function cpClaude(b){var q=val();if(!q){document.getElementById('q').focus();return}
cp('帮我查询第二大脑:'+q+'\\n(走 Query 工作流:综合库内页面与 material 素材卡,必要时联网补缺并标注「库内/联网」;有价值就落 _wiki/outputs/ 加 dimension 并在 log 记一条 query。)',b)}
function cpEngine(b){var q=val();if(!q){document.getElementById('q').focus();return}
cp('cd ~/mind && sage-wiki query "'+q.replace(/"/g,'\\\\"')+'"',b)}
function runUpdate(b){var a=document.getElementById('ans');a.style.display='block';
a.innerHTML='<div class=anst>🔄 全量更新启动中…(日报→编译→索引→lint→保鲜→决策→门户→文档站,通常数分钟)</div>';
b.disabled=true;
fetch(API+'/api/update-all',{method:'POST'}).then(function(r){return r.json()}).then(function(j){
if(!j.ok){a.innerHTML='<div class=anst>❌ '+esc(j.error||'启动失败')+'</div>';b.disabled=false;return}
pollUpdate(b)}).catch(function(e){
a.innerHTML='<div class=anst>❌ 连接失败:'+esc(String(e))+'(全量更新需本地服务)</div>';b.disabled=false})}
function pollUpdate(b){var a=document.getElementById('ans');
var timer=setInterval(function(){fetch(API+'/api/update-status').then(function(r){return r.json()})
.then(function(s){var log=s.log?('<div class=ansb>'+esc(s.log)+'</div>'):'';
if(s.running){a.innerHTML='<div class=anst>🔄 全量更新进行中…(可离开,任务在本机后台跑)</div>'+log}
else{clearInterval(timer);b.disabled=false;var ok=(s.returncode===0);
a.innerHTML='<div class=anst>'+(ok?'✅ 全量更新完成':'⚠️ 完成但有失败(退出码 '+esc(s.returncode)+',见下方日志)')
+' · 刷新页面看最新计数</div>'+log}})
.catch(function(){clearInterval(timer);b.disabled=false;
a.innerHTML='<div class=anst>❌ 轮询中断(本地服务可能停了)</div>'})},1500)}
</script>"""


def build_hero():
    entries, week = query_stats()
    chips = "".join(f'<button class=chip onclick="chip(\'{d}\')">{d}</button>' for d in DIM_TPL)
    kanban = OUT / "wiki" / "五维决策看板.html"
    kanban_btn = ('<a class="btn sec" href="wiki/五维决策看板.html">📊 五维看板</a>'
                  if kanban.exists() else "")
    ok = ' style="color:#16a34a"' if week >= WEEK_TARGET else ""
    last = f' · 上次:{entries[-1][0]}' if entries else " · 还没有过调用,今天开张?"
    score = (f'<div class=score>本周调用 <b{ok}>{week} / {WEEK_TARGET}</b>'
             f' · 累计 <b>{len(entries)}</b> 次{last}</div>')
    rec = recent_decisions()
    rec_html = ""
    if rec:
        items = []
        for d, t, href, dims in rec:
            label = f'{html.escape(t)} <span style="color:var(--mut)">({d} · {html.escape(dims)})</span>'
            item = f'<a href="{href}">{label}</a>' if href else label
            items.append(f'<li>📌 {item}</li>')
        rec_html = '<ul class=recent>' + "".join(items) + '</ul>'
    return (
        '<div class=hero><h2>🎯 问一下第二大脑</h2>'
        '<p class=hint>引擎查事实(概念/摘要)· Claude 查综合(含素材卡 + 联网补缺)· 重决策走 /boss。'
        '答案落 outputs 加 dimension,自动进五维看板与调用计数。</p>'
        '<textarea id=q placeholder="本周真在纠结的问题…(点下面的维度芯片可套查询模板)"></textarea>'
        f'<div class=chips>{chips}</div>'
        '<div class=btns>'
        '<button class=btn id=goq onclick="runQuery(this)" disabled title="检测本地服务中…">🚀 在线查询</button>'
        '<button class="btn sec" onclick="cpClaude(this)">🤖 复制给 Claude</button>'
        '<button class="btn sec" onclick="cpEngine(this)">⚙️ 复制引擎命令</button>'
        f'{kanban_btn}'
        '<button class="btn sec" id=upd onclick="runUpdate(this)" disabled '
        'title="检测本地服务中…">🔄 全量更新</button>'
        '<span id=srv class=srvhint></span></div>'
        '<div id=ans class=ans style="display:none"></div>'
        f'{score}{rec_html}'
        + HERO_JS.replace("%TPL%", json.dumps(DIM_TPL, ensure_ascii=False))
        + '</div>'
    )


def main():
    wiki_pages = n(("browse/wiki", "*.html"))
    concepts = n(("_wiki/concepts", "*.md"))
    outputs = n(("_wiki/outputs", "*.md"))
    material = n(("material", "**/*.md"))
    wiki_exists = (OUT / "wiki" / "index.html").exists()

    cards = []
    cards.append(card("📚", "知识库 Wiki", "编译产出 + 精编素材:概念、摘要、查询产出、六类写作素材,页面互链。",
                      ([("打开 →", "wiki/index.html"), ("关系图", "wiki/graph.html")] if wiki_exists
                       else [("(未生成,跑 build-wiki-site.py)", "#")]),
                      f"{wiki_pages} 页" if wiki_exists else ""))
    subs_exists = (OUT / "subscriptions" / "index.html").exists()
    subs_cnt = ""
    if subs_exists:
        try:
            import subscriptions as S
            rows = S.load()
            due = sum(1 for r in rows if r["left"] <= S.WARN_DAYS)
            subs_cnt = f"{len(rows)} 项" + (f" · {due} 临期" if due else "")
        except Exception:
            subs_cnt = ""
    cards.append(card("💳", "订阅台账", "Claude Code / Codex / VPN / VPS 等数字订阅:周期、费用、下次续费日,临期标红。",
                      ([("打开 →", "subscriptions/index.html")] if subs_exists
                       else [("(未生成,跑 build-subscriptions-site.py)", "#")]),
                      subs_cnt))
    cards.append(card("📄", "产品文档", "PRD、安装/使用/FAQ/服务器部署指南(与公开文档站同源,在 site/)。",
                      [("PRD", "../site/prd.html"), ("使用", "../site/usage.html"),
                       ("安装", "../site/install.html"), ("FAQ", "../site/faq.html")]))

    stat = f"知识库 {concepts} 概念 / {outputs} 产出 / {material} 素材"

    hero = build_hero()

    page = f"""<!DOCTYPE html><html lang=zh><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>第二大脑 · 个人信息入口</title><style>
:root{{--bg:#fafafa;--fg:#1a1a1a;--mut:#666;--line:#e5e5e5;--acc:#2563eb;--card:#fff}}
@media(prefers-color-scheme:dark){{:root{{--bg:#131519;--fg:#e6e6e6;--mut:#9aa0a6;--line:#2a2d33;--acc:#6ea8fe;--card:#1c1f25}}}}
*{{box-sizing:border-box}}body{{margin:0;font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft Yahei",sans-serif;background:var(--bg);color:var(--fg)}}
.wrap{{max-width:860px;margin:0 auto;padding:48px 22px 80px}}
h1{{font-size:2em;margin:0 0 .1em}}.sub{{color:var(--mut);margin:0 0 6px}}
.stat{{color:var(--mut);font-size:.85em;border-bottom:1px solid var(--line);padding-bottom:16px;margin-bottom:24px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:16px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:20px 22px}}
.ct{{display:flex;align-items:center;gap:10px;margin-bottom:6px}}.ic{{font-size:1.5em}}.tt{{font-size:1.15em;font-weight:600}}
.cnt{{margin-left:auto;font-size:.8em;color:var(--mut);background:var(--bg);border:1px solid var(--line);border-radius:20px;padding:2px 10px}}
.ds{{color:var(--mut);font-size:.9em;margin:.3em 0 .9em}}
.lk a{{color:var(--acc);text-decoration:none;font-weight:500}}.lk a:hover{{text-decoration:underline}}
a{{color:var(--acc)}}.foot{{color:var(--mut);font-size:.8em;margin-top:32px;text-align:center}}
.hero{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:20px 22px;margin-bottom:20px}}
.hero h2{{margin:0 0 4px;font-size:1.15em}}.hero .hint{{color:var(--mut);font-size:.82em;margin:0 0 10px}}
.hero textarea{{width:100%;min-height:64px;resize:vertical;border:1px solid var(--line);border-radius:10px;background:var(--bg);color:var(--fg);padding:10px 12px;font:inherit;font-size:.95em}}
.chips{{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0}}
.chip{{border:1px solid var(--line);background:var(--bg);color:var(--mut);border-radius:20px;padding:3px 12px;font-size:.82em;cursor:pointer;font-family:inherit}}
.chip:hover{{border-color:var(--acc);color:var(--acc)}}
.btns{{display:flex;flex-wrap:wrap;gap:10px;margin:4px 0 12px;align-items:center}}
.btn{{border:1px solid var(--acc);background:var(--acc);color:#fff;border-radius:10px;padding:7px 16px;font:inherit;font-size:.9em;cursor:pointer;text-decoration:none;display:inline-block}}
.btn.sec{{background:transparent;color:var(--acc)}}
.score{{display:flex;flex-wrap:wrap;gap:8px 18px;align-items:center;color:var(--mut);font-size:.85em;border-top:1px dashed var(--line);padding-top:12px}}
.score b{{color:var(--fg)}}
.recent{{margin:8px 0 0;padding:0;list-style:none;font-size:.85em}}.recent li{{margin:3px 0}}
.btn:disabled{{opacity:.45;cursor:not-allowed}}
.srvhint{{color:var(--mut);font-size:.78em}}
.ans{{border:1px solid var(--line);border-radius:10px;background:var(--bg);padding:12px 14px;margin:0 0 12px;font-size:.9em}}
.anst{{color:var(--mut);font-size:.85em;margin-bottom:8px}}
.ansb{{white-space:pre-wrap;overflow-x:auto}}
</style></head><body><div class=wrap>
<h1>🧠 第二大脑</h1><p class=sub>个人信息入口 · 本地私密(不公开部署)</p>
<div class=stat>{stat}</div>
{hero}
<div class=grid>{''.join(cards)}</div>
<p class=foot>生成 {datetime.now().strftime('%Y-%m-%d %H:%M')} · build-portal.py 再生 · 仅本地 file:// 可用,不随 aip.cab 部署</p>
</div></body></html>"""

    OUT.mkdir(exist_ok=True)
    (OUT / "index.html").write_text(page, encoding="utf-8")
    print(f"✅ 个人入口已生成:{OUT/'index.html'}")
    print(f"   打开:open {OUT/'index.html'}")


if __name__ == "__main__":
    main()
