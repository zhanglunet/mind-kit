#!/usr/bin/env python3
# scripts/build-wiki-site.py
# 从 _wiki/ + material/ 生成本地可浏览的静态知识库网页 → browse/wiki/。
# 直接 file:// 打开 browse/wiki/index.html 即可(自包含,无需服务器、不联网)。
# 特性:
#   - 首页索引(概念按类型 / 摘要 / 查询产出 / 六类写作素材)
#   - 每页渲染、[[wikilink]] 跨 _wiki↔material 互跳、侧栏导航 + 前端搜索
#   - 关系图 graph.html:谁链谁(实线=[[wikilink]],虚线=概念→其来源摘要),力导向 + 可拖拽
# 依赖:python-markdown(pip install markdown)。建议 compile 后运行。
#
# 用法:python3 scripts/build-wiki-site.py

import html
import json
import re
import shutil
import urllib.parse
from datetime import date
from pathlib import Path

import markdown

VAULT = Path(__file__).resolve().parent.parent
WIKI = VAULT / "_wiki"
MATERIAL = VAULT / "material"
OUT = VAULT / "browse" / "wiki"   # 本地私密浏览站(browse/ 整目录 gitignore,不随公开 site/ 部署)
WIKILINK = re.compile(r"\[\[([^\]|]+?)(?:\|([^\]]+))?\]\]")

# material 子目录 → (展示标签, 排序);对齐 CLAUDE.md 六类框架
MAT_LABELS = {
    "quotes": "① 金句",
    "stories": "② 经历复盘",
    "references": "③ 外部信号",
    "cases": "④ 案例",
    "frameworks": "⑤ 框架",
    "data": "⑥ 数据趋势",
}
# 概念类型组动态排前;这些固定组按此顺序排后
TAIL_ORDER = ["摘要", "产出"] + list(MAT_LABELS.values())

# 节点配色(关系图 + 首页 chip)
KIND_COLOR = {"concept": "#33a98a", "summary": "#b0703a", "output": "#5b47d6", "material": "#e0873a"}
KIND_LABEL = {"concept": "概念", "summary": "摘要", "output": "产出", "material": "素材"}

# 概念组(entity_type)英文原始名 → 中文显示;未知类型原样显示
GROUP_DISP = {"concept": "概念", "claim": "论断", "technique": "方法"}


def disp(name):
    return GROUP_DISP.get(name, name)


def split_fm(text):
    fm, body = {}, text
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            for line in text[3:end].strip("\n").splitlines():
                m = re.match(r"^([A-Za-z_一-鿿]+):\s*(.*)$", line)
                if m:
                    fm[m.group(1)] = m.group(2).strip().strip('"')
            body = text[end + 4:].lstrip("\n")
    return fm, body


def first_sentence(body, n=100):
    for line in body.splitlines():
        s = line.strip()
        if not s or s.startswith(("#", ">", "![", "|", "```", "---")):
            continue
        s = WIKILINK.sub(lambda m: m.group(2) or m.group(1), s)
        s = re.sub(r"[*`_]", "", s)
        return (s[:n] + "…") if len(s) > n else s
    return ""


def h1(body, fallback):
    m = re.search(r"^#\s+(.+)$", body, re.M)
    return m.group(1).strip() if m else fallback


class Page:
    def __init__(self, path, kind, group):
        self.path = path
        self.slug = path.stem
        self.mtime = path.stat().st_mtime   # 首页「最近更新」按它排序
        fm, body = split_fm(path.read_text(encoding="utf-8"))
        self.fm, self.body = fm, body
        self.kind = kind
        self.group = group
        self.title = fm.get("title") or h1(body, self.slug)
        self.oneliner = first_sentence(body)
        try:
            self.source_list = json.loads(fm.get("sources", "[]"))
        except Exception:
            self.source_list = []
        self.sources = len(self.source_list)

    @property
    def href(self):
        return urllib.parse.quote(self.slug) + ".html"


def collect():
    pages = []
    for f in sorted((WIKI / "concepts").glob("*.md")):
        fm, _ = split_fm(f.read_text(encoding="utf-8"))
        pages.append(Page(f, "concept", fm.get("entity_type", "concept")))
    for f in sorted((WIKI / "summaries").glob("*.md")):
        pages.append(Page(f, "summary", "摘要"))
    for f in sorted((WIKI / "outputs").glob("*.md")):
        pages.append(Page(f, "output", "产出"))
    # 六类写作素材
    for sub, label in MAT_LABELS.items():
        for f in sorted((MATERIAL / sub).glob("*.md")):
            pages.append(Page(f, "material", label))
    return pages


def grouped(pages):
    g = {}
    for p in pages:
        g.setdefault(p.group, []).append(p)
    for k in g:
        g[k].sort(key=lambda p: p.title.lower())
    concept_groups = sorted(k for k in g if k not in TAIL_ORDER)
    return [(k, g[k]) for k in concept_groups + [x for x in TAIL_ORDER if x in g]]


def source_to_summary_slug(src):
    # "raw/clippings/新加坡….md" → 摘要页 slug "raw-clippings-新加坡…"
    return src[:-3].replace("/", "-") if src.endswith(".md") else src.replace("/", "-")


def build_edges(pages, lookup):
    """实线:已解析的 [[wikilink]];虚线:概念 → 其来源摘要。去重、去自环。"""
    slugs = {p.slug for p in pages}
    seen, edges = set(), []

    def add(s, t, typ):
        if s == t or s not in slugs or t not in slugs:
            return
        key = (s, t, typ)
        if key not in seen:
            seen.add(key)
            edges.append({"s": s, "t": t, "type": typ})

    for p in pages:
        for m in WIKILINK.finditer(p.body):
            tgt = lookup.get(m.group(1).strip().lower())
            if tgt:
                add(p.slug, tgt.slug, "link")
        if p.kind == "concept":
            for src in p.source_list:
                sm = source_to_summary_slug(src)
                if sm in slugs:
                    add(p.slug, sm, "src")
    return edges


def sidebar_html(groups, active_slug):
    li = []
    for name, ps in groups:
        open_attr = " open" if any(p.slug == active_slug for p in ps) else ""
        li.append(f'<details class="nav-group"{open_attr}>')
        li.append(f'<summary class="grp">{html.escape(disp(name))}<span class="nav-count">{len(ps)}</span></summary>')
        for p in ps:
            cls = " active" if p.slug == active_slug else ""
            li.append(f'<a class="nav{cls}" href="{p.href}" data-t="{html.escape(p.title.lower())}">{html.escape(p.title)}</a>')
        li.append('</details>')
    return "\n".join(li)


def page_shell(title, sidebar, main, home_active=False, graph_active=False):
    home_cls = " active" if home_active else ""
    graph_cls = " active" if graph_active else ""
    return f"""<!doctype html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)} · 第二大脑</title>
<link rel="stylesheet" href="style.css"></head>
<body>
<button id="menu" aria-label="menu">☰</button>
<aside id="side">
  <a class="brand{home_cls}" href="index.html">🧠 第二大脑</a>
  <a class="glink{graph_cls}" href="graph.html">🕸 关系图</a>
  <input id="q" placeholder="搜索页面…" autocomplete="off">
  <nav id="nav">
{sidebar}
  </nav>
</aside>
<main>{main}</main>
<script>
const q=document.getElementById('q'),nav=document.getElementById('nav');
q&&q.addEventListener('input',()=>{{const v=q.value.toLowerCase();
 nav.querySelectorAll('.nav').forEach(a=>{{a.style.display=a.dataset.t.includes(v)||a.textContent.toLowerCase().includes(v)?'':'none';}});
 nav.querySelectorAll('.nav-group').forEach(g=>{{const any=[...g.querySelectorAll('.nav')].some(a=>a.style.display!=='none');
  g.style.display=any?'':'none';if(v&&any)g.open=true;}});}});
document.getElementById('menu').addEventListener('click',()=>document.getElementById('side').classList.toggle('open'));
</script>
</body></html>"""


def meta_chips(p):
    chips = [f'<span class="chip kind-{p.kind}">{KIND_LABEL[p.kind]}</span>']
    if p.group not in ("摘要", "产出"):
        chips.append(f'<span class="chip">{html.escape(p.group)}</span>')
    if p.sources:
        chips.append(f'<span class="chip">{p.sources} 源</span>')
    if p.kind == "material" and p.fm.get("主体"):
        subj = p.fm["主体"]
        chips.append(f'<span class="chip">{html.escape(subj[:24] + ("…" if len(subj) > 24 else ""))}</span>')
    for key in ("dimension", "date", "ingested"):
        if p.fm.get(key):
            chips.append(f'<span class="chip">{html.escape(p.fm[key])}</span>')
    return '<div class="chips">' + "".join(chips) + "</div>"


def render_body(body, lookup):
    def repl(m):
        target = m.group(1).strip()
        alias = m.group(2)
        p = lookup.get(target.lower())
        label = alias or (p.title if p else target)
        if p:
            return f"[{label}]({p.href})"
        return f"<span class='broken'>{html.escape(label)}</span>"
    md = markdown.Markdown(extensions=["tables", "fenced_code", "sane_lists"])
    return md.convert(WIKILINK.sub(repl, body))


def group_kind(name):
    """分组名 → 节点类别(决定索引芯片色点,与关系图配色一致)。"""
    if name == "摘要":
        return "summary"
    if name == "产出":
        return "output"
    if name in MAT_LABELS.values():
        return "material"
    return "concept"


def recent_html(pages, limit=10):
    """「最近更新」区块:按源文件 mtime 降序取前 N 页——新 ingest 的内容
    一打开首页就能看到,不用在几百页的分类索引里找。"""
    recent = sorted(pages, key=lambda p: p.mtime, reverse=True)[:limit]
    items = "\n".join(
        f'<li><span class="date">{date.fromtimestamp(p.mtime).isoformat()}</span> '
        f'<a href="{p.href}">{html.escape(p.title)}</a> '
        f'<span class="src">{html.escape(disp(p.group))}</span></li>'
        for p in recent)
    return f'<h2 id="recent">最近更新 <span class="cnt">{len(recent)}</span></h2>\n<ul class="cards">\n{items}\n</ul>'


def index_main(groups, pages):
    n = len(pages)
    # 头部粘性分类索引:每组一个锚点芯片(色点=类别色 + 计数),长页一键跳段
    toc = "".join(
        f'<a class="tchip" href="#g{i}"><i style="background:{KIND_COLOR[group_kind(name)]}"></i>'
        f'{html.escape(disp(name))}<b>{len(ps)}</b></a>'
        for i, (name, ps) in enumerate(groups))
    category_cards = "".join(
        f'<a class="category-card" href="#g{i}">'
        f'<span class="category-dot" style="background:{KIND_COLOR[group_kind(name)]}"></span>'
        f'<span><strong>{html.escape(disp(name))}</strong><small>{len(ps)} 页</small></span>'
        f'</a>'
        for i, (name, ps) in enumerate(groups))
    parts = [f"<h1>知识库索引</h1>",
             f'<p class="sub">共 {n} 页 · 生成于 {date.today().isoformat()} · 由 <code>build-wiki-site.py</code> 从 <code>_wiki/</code> + <code>material/</code> 生成 · <a href="graph.html">🕸 看关系图</a></p>',
             recent_html(pages),
             '<h2 class="overview-title">按分类浏览</h2>',
             f'<div class="category-grid">{category_cards}</div>',
             f'<div class="toc">{toc}</div>']
    for i, (name, ps) in enumerate(groups):
        parts.append(f'<details class="index-section" id="g{i}">')
        parts.append(f'<summary><span>{html.escape(disp(name))}</span><span class="cnt">{len(ps)} 页</span></summary>')
        parts.append('<ul class="cards">')
        for p in ps:
            one = f' — {html.escape(p.oneliner)}' if p.oneliner else ""
            src = f' <span class="src">{p.sources}源</span>' if p.sources else ""
            parts.append(f'<li><a href="{p.href}">{html.escape(p.title)}</a>{src}{one}</li>')
        parts.append("</ul>")
        parts.append("</details>")
    return "\n".join(parts)


def graph_main(pages, edges):
    nodes = [{"id": p.slug, "label": p.title, "kind": p.kind, "href": p.href} for p in pages]
    legend = "".join(
        f'<span class="lg"><i style="background:{KIND_COLOR[k]}"></i>{KIND_LABEL[k]}</span>'
        for k in ("concept", "summary", "output", "material"))
    n_link = sum(1 for e in edges if e["type"] == "link")
    n_src = sum(1 for e in edges if e["type"] == "src")
    tmpl = """<h1>关系图</h1>
<p class="sub">__NN__ 个节点 · __NL__ 条链接(实线=[[wikilink]])+ __NS__ 条来源关系(虚线=概念→来源摘要)。拖拽节点可调整,点击进入页面。</p>
<div class="legend">__LEGEND__</div>
<div id="gwrap"><svg id="g" viewBox="0 0 940 700" preserveAspectRatio="xMidYMid meet"></svg></div>
<script>
const NODES=__NODES__, EDGES=__EDGES__, KC=__KC__;
const W=940,H=700,cx=W/2,cy=H/2,idx={};
NODES.forEach((n,i)=>{idx[n.id]=i;n.x=cx+(Math.random()-.5)*520;n.y=cy+(Math.random()-.5)*380;n.vx=0;n.vy=0;n.deg=0;});
const L=EDGES.map(e=>({s:idx[e.s],t:idx[e.t],type:e.type})).filter(l=>l.s!=null&&l.t!=null);
L.forEach(l=>{NODES[l.s].deg++;NODES[l.t].deg++;});
for(let it=0;it<320;it++){
  const k=it<220?1:.35;
  for(let i=0;i<NODES.length;i++)for(let j=i+1;j<NODES.length;j++){
    let a=NODES[i],b=NODES[j],dx=a.x-b.x,dy=a.y-b.y,d2=dx*dx+dy*dy||1,d=Math.sqrt(d2),f=2600/d2;
    dx/=d;dy/=d;a.vx+=dx*f;a.vy+=dy*f;b.vx-=dx*f;b.vy-=dy*f;}
  L.forEach(l=>{let a=NODES[l.s],b=NODES[l.t],dx=b.x-a.x,dy=b.y-a.y,d=Math.sqrt(dx*dx+dy*dy)||1,f=(d-96)*.02;
    dx/=d;dy/=d;a.vx+=dx*f;a.vy+=dy*f;b.vx-=dx*f;b.vy-=dy*f;});
  NODES.forEach(n=>{n.vx+=(cx-n.x)*.008;n.vy+=(cy-n.y)*.008;n.x+=n.vx*k;n.y+=n.vy*k;n.vx*=.85;n.vy*=.85;
    n.x=Math.max(24,Math.min(W-24,n.x));n.y=Math.max(24,Math.min(H-24,n.y));});
}
const svg=document.getElementById('g'),NS='http://www.w3.org/2000/svg';
const el=(t,a)=>{const e=document.createElementNS(NS,t);for(const k in a)e.setAttribute(k,a[k]);return e;};
const lines=L.map(l=>{const ln=el('line',{class:'edge '+l.type});svg.appendChild(ln);return ln;});
const R=n=>5+Math.min(9,n.deg*1.3);
const gnodes=NODES.map((n,i)=>{
  const g=el('g',{class:'node',transform:`translate(${n.x},${n.y})`});
  const c=el('circle',{r:R(n),fill:KC[n.kind]||'#888'});
  const tx=el('text',{x:R(n)+3,y:4});tx.textContent=n.label;
  g.appendChild(c);g.appendChild(tx);g.dataset.i=i;
  g.addEventListener('click',ev=>{if(!g.dataset.drag)location.href=n.href;});
  svg.appendChild(g);return g;});
function draw(){
  L.forEach((l,i)=>{const a=NODES[l.s],b=NODES[l.t];lines[i].setAttribute('x1',a.x);lines[i].setAttribute('y1',a.y);
    lines[i].setAttribute('x2',b.x);lines[i].setAttribute('y2',b.y);});
  NODES.forEach((n,i)=>gnodes[i].setAttribute('transform',`translate(${n.x},${n.y})`));}
draw();
// 拖拽
let drag=null;
function pt(ev){const r=svg.getBoundingClientRect(),cl=ev.touches?ev.touches[0]:ev;
  return {x:(cl.clientX-r.left)/r.width*W,y:(cl.clientY-r.top)/r.height*H};}
svg.addEventListener('mousedown',ev=>{const g=ev.target.closest('.node');if(!g)return;
  drag=+g.dataset.i;g.dataset.drag=1;ev.preventDefault();});
window.addEventListener('mousemove',ev=>{if(drag==null)return;const p=pt(ev);NODES[drag].x=p.x;NODES[drag].y=p.y;draw();});
window.addEventListener('mouseup',()=>{if(drag!=null){const g=gnodes[drag];setTimeout(()=>{delete g.dataset.drag;},30);}drag=null;});
// 悬停高亮邻居
gnodes.forEach((g,i)=>g.addEventListener('mouseenter',()=>{
  const nb=new Set([i]);L.forEach(l=>{if(l.s===i)nb.add(l.t);if(l.t===i)nb.add(l.s);});
  gnodes.forEach((h,j)=>h.style.opacity=nb.has(j)?1:.18);
  lines.forEach((ln,k)=>ln.style.opacity=(L[k].s===i||L[k].t===i)?.9:.05);}));
svg.addEventListener('mouseleave',()=>{gnodes.forEach(h=>h.style.opacity=1);lines.forEach(ln=>ln.style.opacity='');});
</script>"""
    return (tmpl
            .replace("__NN__", str(len(nodes)))
            .replace("__NL__", str(n_link))
            .replace("__NS__", str(n_src))
            .replace("__LEGEND__", legend)
            .replace("__NODES__", json.dumps(nodes, ensure_ascii=False))
            .replace("__EDGES__", json.dumps(edges, ensure_ascii=False))
            .replace("__KC__", json.dumps(KIND_COLOR)))


CSS = """
:root{--bg:#fff;--fg:#1a1a1a;--mut:#666;--line:#e5e5e5;--acc:#5b47d6;--side:#f7f7f8;--chip:#eee;--code:#f2f2f4}
@media(prefers-color-scheme:dark){:root{--bg:#16171a;--fg:#e6e6e6;--mut:#9a9aa0;--line:#2b2c30;--acc:#a99bff;--side:#1c1d21;--chip:#26272c;--code:#1f2024}}
*{box-sizing:border-box}html,body{margin:0}body{font:16px/1.65 -apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft Yahei",sans-serif;color:var(--fg);background:var(--bg)}
#side{position:fixed;top:0;left:0;width:280px;height:100vh;overflow-y:auto;background:var(--side);border-right:1px solid var(--line);padding:16px 12px}
.brand{display:block;font-weight:700;font-size:18px;color:var(--fg);text-decoration:none;padding:6px 8px;margin-bottom:6px}
.glink{display:block;color:var(--acc);text-decoration:none;font-size:14px;padding:5px 8px;border-radius:6px;margin-bottom:10px}
.glink:hover{background:var(--chip)}.glink.active{background:var(--acc);color:#fff}
#q{width:100%;padding:8px 10px;border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--fg);margin-bottom:10px;font-size:14px}
.nav-group{margin:10px 0}.grp{display:flex;align-items:center;justify-content:space-between;font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:var(--mut);margin:0;padding:4px 8px;cursor:pointer;list-style:none}.grp::-webkit-details-marker{display:none}.grp::before{content:'›';font-size:16px;margin-right:5px;transition:.15s}.nav-group[open]>.grp::before{transform:rotate(90deg)}
.nav-count{font-size:11px;opacity:.65;font-variant-numeric:tabular-nums}
a.nav{display:block;padding:5px 8px;border-radius:6px;color:var(--fg);text-decoration:none;font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
a.nav:hover{background:var(--chip)}a.nav.active{background:var(--acc);color:#fff}
main{margin-left:280px;padding:36px 48px;max-width:860px}
h1{font-size:28px;margin:.2em 0 .4em}h2{font-size:20px;margin:1.4em 0 .5em;border-bottom:1px solid var(--line);padding-bottom:.2em}
h3{font-size:16px;margin:1.2em 0 .4em}.sub{color:var(--mut);font-size:14px}
a{color:var(--acc)}.broken{color:var(--mut);text-decoration:underline dotted}
.back{font-size:13px;color:var(--mut);text-decoration:none}
.chips{margin:.2em 0 1.2em;display:flex;gap:6px;flex-wrap:wrap}
.chip{background:var(--chip);color:var(--mut);font-size:12px;padding:2px 8px;border-radius:20px}
.chip.kind-output{background:var(--acc);color:#fff}.chip.kind-concept{background:#33a98a;color:#fff}
.chip.kind-summary{background:#b0703a;color:#fff}.chip.kind-material{background:#e0873a;color:#fff}
.cnt{color:var(--mut);font-size:14px;font-weight:400}
.toc{position:sticky;top:0;z-index:5;background:var(--bg);display:flex;flex-wrap:wrap;gap:8px;padding:10px 0;margin:6px 0 4px;border-bottom:1px solid var(--line)}
.tchip{display:inline-flex;align-items:center;gap:6px;font-size:13px;color:var(--fg);text-decoration:none;background:var(--chip);border-radius:20px;padding:3px 10px;white-space:nowrap}
.tchip:hover{background:var(--acc);color:#fff}
.tchip i{width:8px;height:8px;border-radius:50%;display:inline-block;flex:none}
.tchip b{font-weight:600;color:inherit;opacity:.65;margin-left:2px}
h2{scroll-margin-top:64px}
.overview-title{margin-top:1.2em}.category-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:8px 0 18px}.category-card{display:flex;align-items:center;gap:10px;padding:12px;border:1px solid var(--line);border-radius:10px;color:var(--fg);text-decoration:none;background:var(--side);transition:.15s}.category-card:hover{border-color:var(--acc);transform:translateY(-1px)}.category-dot{width:10px;height:10px;border-radius:50%;flex:none}.category-card strong,.category-card small{display:block}.category-card strong{font-size:14px}.category-card small{font-size:12px;color:var(--mut);margin-top:2px}
.index-section{border-bottom:1px solid var(--line);scroll-margin-top:64px}.index-section>summary{display:flex;align-items:center;justify-content:space-between;cursor:pointer;list-style:none;font-size:20px;font-weight:600;padding:12px 0}.index-section>summary::-webkit-details-marker{display:none}.index-section>summary::before{content:'›';font-size:24px;font-weight:400;color:var(--mut);margin-right:8px;transition:.15s}.index-section[open]>summary::before{transform:rotate(90deg)}.index-section>summary>span:first-of-type{margin-right:auto}.index-section .cards{margin:0 0 14px 32px}
ul.cards{list-style:none;padding:0}ul.cards li{padding:8px 0;border-bottom:1px solid var(--line)}
ul.cards li a{font-weight:600}.src{background:var(--chip);color:var(--mut);font-size:12px;padding:1px 6px;border-radius:10px;margin-left:4px}
.date{color:var(--mut);font-size:13px;font-variant-numeric:tabular-nums;margin-right:6px}
code{background:var(--code);padding:1px 5px;border-radius:4px;font-size:.9em}pre{background:var(--code);padding:14px;border-radius:8px;overflow-x:auto}
pre code{background:none;padding:0}table{border-collapse:collapse;width:100%;display:block;overflow-x:auto;font-size:14px}
th,td{border:1px solid var(--line);padding:6px 10px;text-align:left}th{background:var(--chip)}
blockquote{border-left:3px solid var(--acc);margin:1em 0;padding:.2em 1em;color:var(--mut)}
.legend{display:flex;gap:14px;flex-wrap:wrap;margin:.4em 0 1em;font-size:13px;color:var(--mut)}
.legend .lg{display:flex;align-items:center;gap:5px}.legend i{width:12px;height:12px;border-radius:50%;display:inline-block}
#gwrap{border:1px solid var(--line);border-radius:10px;background:var(--bg);overflow:hidden}
svg#g{width:100%;height:auto;display:block;touch-action:none}
svg#g .edge{stroke:var(--line)}svg#g .edge.link{stroke:var(--acc);stroke-opacity:.5}
svg#g .edge.src{stroke:var(--mut);stroke-opacity:.35;stroke-dasharray:4 3}
svg#g .node{cursor:pointer}svg#g .node circle{stroke:var(--bg);stroke-width:1.5}
svg#g .node text{font-size:11px;fill:var(--fg);paint-order:stroke;stroke:var(--bg);stroke-width:3px;pointer-events:none}
#menu{display:none}
@media(max-width:820px){#side{transform:translateX(-100%);transition:.2s;z-index:9}#side.open{transform:none}main{margin-left:0;padding:56px 20px}
#menu{display:block;position:fixed;top:10px;left:10px;z-index:10;background:var(--acc);color:#fff;border:0;border-radius:8px;padding:6px 12px;font-size:18px}}
"""


def main():
    # 指纹在渲染之前算(P0-3b):若构建期间文件被并发修改,manifest 记录的是"更旧"的输入
    # → ping 只会误报 stale(触发一次多余重建),绝不会把过期站点误判为新鲜(fail-safe 方向)。
    import indexlib
    fp = indexlib.input_fingerprint(indexlib.browse_inputs(VAULT), base=VAULT)

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    (OUT / "style.css").write_text(CSS, encoding="utf-8")

    pages = collect()
    lookup = {}
    for p in pages:
        lookup[p.slug.lower()] = p
        lookup[p.title.lower()] = p
    groups = grouped(pages)
    edges = build_edges(pages, lookup)

    # 首页
    (OUT / "index.html").write_text(
        page_shell("知识库索引", sidebar_html(groups, ""), index_main(groups, pages), home_active=True),
        encoding="utf-8")

    # 关系图
    (OUT / "graph.html").write_text(
        page_shell("关系图", sidebar_html(groups, ""), graph_main(pages, edges), graph_active=True),
        encoding="utf-8")

    # 每页(文件名用原始 slug;href 才编码 —— 浏览器解码 href 正好对上原始文件名)
    for p in pages:
        main_html = f'<a class="back" href="index.html">← 索引</a><h1>{html.escape(p.title)}</h1>{meta_chips(p)}{render_body(p.body, lookup)}'
        (OUT / (p.slug + ".html")).write_text(
            page_shell(p.title, sidebar_html(groups, p.slug), main_html),
            encoding="utf-8")

    # 落 manifest:brain-server /api/ping 据此判断浏览站是否已过期(指纹已在渲染前算好)
    from datetime import datetime
    (OUT / ".build-manifest.json").write_text(json.dumps({
        "schema_version": indexlib.MANIFEST_SCHEMA,
        "fingerprint": fp["fingerprint"], "file_count": fp["file_count"],
        "built_at": datetime.now().isoformat(timespec="seconds"),
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    nc = sum(1 for p in pages if p.kind == "concept")
    ns = sum(1 for p in pages if p.kind == "summary")
    no = sum(1 for p in pages if p.kind == "output")
    nm = sum(1 for p in pages if p.kind == "material")
    nl = sum(1 for e in edges if e["type"] == "link")
    print(f"✅ 知识库网页已生成:{OUT}/index.html")
    print(f"   {len(pages)} 页(概念 {nc} / 摘要 {ns} / 产出 {no} / 素材 {nm})· 关系图 {len(pages)} 节点 / {nl} 链接")
    print(f"   打开:open {OUT/'index.html'}")


if __name__ == "__main__":
    main()
