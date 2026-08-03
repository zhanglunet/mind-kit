#!/usr/bin/env python3
# scripts/brain-server.py — 第二大脑本地服务(纯标准库,零依赖)。
# 让内部首页的「问一下第二大脑」能真·在线查询:
#   1) 静态托管 browse/ + site/ + docs/(http://127.0.0.1:8788/browse/index.html;
#      8787 被系统 reattachd 占着,故用 8788)
#      → 与 API 同源,天然无 CORS 问题;file:// 打开的旧入口也能跨源调 API(已放开 CORS)。
#   2) POST /api/query {"q": "..."} → 子进程跑 `sage-wiki query`(产物照常落 _wiki/under_review/),
#      成功后向 _wiki/log.md 追加一条 `## [日期] query ｜ …(引擎·在线)` → 调用率自动记账。
#   3) GET /api/ping → 探活(首页据此点亮/置灰「在线查询」按钮)。
# 安全:只绑 127.0.0.1;静态目录白名单 {browse, site, docs},路径穿越防护;子进程不走 shell。
# 常驻:配套 scripts/com.mind.brain-server.plist(LaunchAgent,登录自启 + 保活);
#      卸载:launchctl unload ~/Library/LaunchAgents/com.mind.brain-server.plist && rm 同文件。
# 手动跑:python3 scripts/brain-server.py [--port 8788]

import argparse
import json
import mimetypes
import os
import shutil
import subprocess
import sys
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

import searchlib   # 本地检索(P1-1):/api/search 与引擎兜底重查的同义扩展

VAULT = Path(__file__).resolve().parent.parent
STATIC_ROOTS = {"browse", "site", "docs"}   # 只托管这三棵子树
QUERY_TIMEOUT = 600                          # 引擎查询上限(GLM 综合可达数分钟)

# ---- 全量更新(网页一键启动:门户按钮 → 此端点 → scripts/update-all.sh)----
# 单飞:同一时刻只跑一份,重复触发返回 running。输出落 browse/.update-all.log 供轮询回显。
_update_lock = threading.Lock()
_update = {"running": False, "returncode": None, "started_at": None, "finished_at": None}


def _update_log_path():
    return VAULT / "browse" / ".update-all.log"


def _try_flock():
    """非阻塞拿 VAULT/.update-all.lock 文件锁 → fd 或 None。

    _update_lock 只护本进程;还有别的触发方(如定时任务、其他常驻进程)会跑
    update-all,跨进程互斥只能靠文件锁——各方约定同一个锁文件。"""
    import fcntl
    fd = os.open(VAULT / ".update-all.lock", os.O_CREAT | os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fd
    except OSError:
        os.close(fd)
        return None


def _run_update_all(lock_fd):
    """后台执行 update-all.sh,输出落日志,完成后回填状态。单飞由 start_update_all 加锁保证。"""
    script = os.environ.get("MIND_UPDATE_SCRIPT") or str(VAULT / "scripts" / "update-all.sh")
    log = _update_log_path()
    rc = 127
    try:
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("w", encoding="utf-8") as f:
            f.write(f"# update-all 启动 {datetime.now().isoformat(timespec='seconds')}\n")
            f.flush()
            rc = subprocess.run(["bash", script], cwd=str(VAULT),
                                stdout=f, stderr=subprocess.STDOUT, text=True).returncode
    except OSError as e:
        try:
            with _update_log_path().open("a", encoding="utf-8") as f:
                f.write(f"\n# 启动失败:{e}\n")
        except OSError:
            pass
    finally:
        os.close(lock_fd)                 # 释放跨进程锁(进程崩溃时 OS 自动释放)
    with _update_lock:
        _update.update(running=False, returncode=rc,
                       finished_at=datetime.now().isoformat(timespec="seconds"))


def start_update_all():
    """尝试启动全量更新;返回 'started'(新起)或 'running'(已在跑,不重入)。
    双重互斥:线程锁护本进程状态;文件锁护跨进程(别的触发方在跑同样算 running)。"""
    with _update_lock:
        if _update["running"]:
            return "running"
        lock_fd = _try_flock()
        if lock_fd is None:
            return "running"              # 别的进程在跑
        _update.update(running=True, returncode=None, finished_at=None,
                       started_at=datetime.now().isoformat(timespec="seconds"))
    threading.Thread(target=_run_update_all, args=(lock_fd,), daemon=True).start()
    return "started"


def update_status():
    """当前状态 + 日志尾(供门户轮询回显)。"""
    with _update_lock:
        st = dict(_update)
    try:
        st["log"] = _update_log_path().read_text(encoding="utf-8", errors="replace")[-4000:]
    except OSError:
        st["log"] = ""
    return st

# 引擎 BM25 无中文分词:整句长中文当一个词 → 必然无命中(实测 2026-07-16)。
# 兜底:无命中时把问题切成空格分隔的关键词重查一次(实测空格分词后命中良好)。
NOHIT_SENTINEL = "No relevant articles found"
STOPWORDS = ["为什么", "是什么", "哪些", "什么", "怎么", "如何", "面临", "对应",
             "主要", "方向", "问题", "分析", "请问", "帮我", "一下", "以及",
             "的", "了", "吗", "呢", "与", "和", "及", "在", "有", "是", "请"]


def segment(q):
    """无词典的粗分词:去停用词 → 非中英数一律成空格 → 超 6 字的中文长串滚动二元组。"""
    import re as _re
    s = q
    for w in sorted(STOPWORDS, key=len, reverse=True):
        s = s.replace(w, " ")
    s = _re.sub(r"[^一-鿿A-Za-z0-9]+", " ", s)
    parts = []
    for frag in s.split():
        if _re.fullmatch(r"[A-Za-z0-9]+", frag) or len(frag) <= 6:
            parts.append(frag)
        else:
            parts.extend(frag[i:i + 2] for i in range(len(frag) - 1))
    seen, out = set(), []
    for p in parts:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return " ".join(out)


def browse_stale():
    """浏览站是否落后于 vault(P0-3c,"结构可解析 ≠ 索引新鲜")。
    比对 browse/wiki/.build-manifest.json 里的构建指纹与当前 vault 输入指纹:
    true=已过期(该重跑 build-wiki-site.py);false=新鲜;null=未构建/无 manifest(无从判断)。"""
    manifest = VAULT / "browse" / "wiki" / ".build-manifest.json"
    try:
        stored = json.loads(manifest.read_text(encoding="utf-8"))
        if not isinstance(stored, dict):        # 损坏成数组等:不判、不 500
            return None
        import indexlib
        now = indexlib.input_fingerprint(indexlib.browse_inputs(VAULT), base=VAULT)
        return stored.get("fingerprint") != now["fingerprint"]
    except (OSError, ValueError):
        return None


def find_sage():
    p = shutil.which("sage-wiki")
    if p:
        return p
    fallback = Path.home() / "go" / "bin" / "sage-wiki"
    return str(fallback) if fallback.exists() else None


def append_query_log(question):
    """向 _wiki/log.md 追加调用记账(append-only,与 compile.sh 记 lint 同一哲学)。"""
    log = VAULT / "_wiki" / "log.md"
    line = f"\n## [{datetime.now().strftime('%Y-%m-%d')}] query ｜ {question}(引擎·在线)\n"
    try:
        with log.open("a", encoding="utf-8") as f:
            f.write(line)
        return True
    except OSError:
        return False


class Handler(BaseHTTPRequestHandler):
    server_version = "mind-brain/1.0"

    # ---- 基础发送 ----
    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _cors(self):  # 允许 file:// 打开的旧入口跨源调 API(服务只绑回环,无外泄面)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def log_message(self, fmt, *args):  # 精简访问日志
        sys.stderr.write("[%s] %s\n" % (datetime.now().strftime("%H:%M:%S"), fmt % args))

    # ---- 路由 ----
    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def _redirect(self, to):
        self.send_response(302)
        self.send_header("Location", to)
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/ping":
            return self._json(200, {"ok": True, "engine": bool(find_sage()),
                                    "browse_stale": browse_stale()})
        if path == "/api/update-status":
            return self._json(200, {"ok": True, **update_status()})
        if path in ("/", "/index.html"):
            # 302 跳到 /browse/ 下,让页面里的相对链接(wiki/… 等)正确落在白名单子树内;
            # 直接在根路径回内容会让相对链接解析成 /wiki/… → 404(2026-07-16 实测踩坑)。
            return self._redirect("/browse/index.html")
        # 兼容:根路径时代的裸链接 / 旧书签(/wiki/… )→ 302 归位到 /browse/ 下
        top = path.lstrip("/").split("/", 1)[0]
        if top == "wiki":
            return self._redirect("/browse" + path)
        return self._static(path)

    def _local_origin_ok(self):
        """action 端点(触发副作用)的轻量 CSRF 护栏:只放行本地来源。
        无 Origin(curl 等)或 file:// 的 'null' 放行;有 Origin 则须是回环主机。
        (读端点 /api/query·/search 沿用 CORS *,风险面同旧设计;唯有会启动进程的
         /api/update-all 收紧,挡住"访问恶意网页即触发本机重建"。)"""
        origin = self.headers.get("Origin")
        if not origin or origin == "null":
            return True
        return urlparse(origin).hostname in ("127.0.0.1", "localhost", "::1")

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/update-all":
            if not self._local_origin_ok():
                return self._json(403, {"ok": False, "error": "仅限本地来源触发全量更新"})
            return self._json(200, {"ok": True, "status": start_update_all()})
        if path not in ("/api/query", "/api/search"):
            return self._json(404, {"ok": False, "error": "unknown endpoint"})
        try:
            n = int(self.headers.get("Content-Length") or 0)
            data = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
        except (ValueError, UnicodeDecodeError):
            return self._json(400, {"ok": False, "error": "bad json"})
        q = (data.get("q") or "").strip()
        if not q:
            return self._json(400, {"ok": False, "error": "q 不能为空"})

        if path == "/api/search":
            # 秒级本地检索(searchlib 三通道 RRF,不走 LLM):索引内存缓存 + 指纹自动刷新
            try:
                results = searchlib.search(searchlib.get_index(VAULT), q)
            except Exception as e:   # 本地检索坏了不该 500 到没有诊断信息
                return self._json(500, {"ok": False, "error": f"local search failed: {e}"})
            return self._json(200, {"ok": True, "results": results})
        sage = find_sage()
        if not sage:
            return self._json(500, {"ok": False, "error": "找不到 sage-wiki 可执行文件"})

        def run(question):
            return subprocess.run([sage, "query", question], cwd=VAULT,
                                  capture_output=True, text=True, timeout=QUERY_TIMEOUT)

        try:
            r = run(q)
            fallback = False
            if r.returncode == 0 and NOHIT_SENTINEL in r.stdout:
                # 兜底重查:关键词化(治引擎无中文分词)+ 同义组扩展(P1-1c,中英互通召回)
                seg = searchlib.expand_query(segment(q) or q)
                if seg and seg != q:
                    r2 = run(seg)
                    if r2.returncode == 0 and NOHIT_SENTINEL not in r2.stdout:
                        r, fallback = r2, True
        except subprocess.TimeoutExpired:
            return self._json(504, {"ok": False, "error": f"查询超时(>{QUERY_TIMEOUT}s)"})
        if r.returncode != 0:
            tail = (r.stderr or r.stdout or "").strip()[-800:]
            return self._json(502, {"ok": False, "error": f"引擎退出码 {r.returncode}", "detail": tail})
        answer = r.stdout.strip()
        hit = NOHIT_SENTINEL not in answer
        # 评测流量(evaluate_search.py 带 eval:true)不记账:回归 case 批量查询不掺水调用率
        is_eval = bool(data.get("eval"))
        logged = append_query_log(q) if (hit and not is_eval) else False
        return self._json(200, {"ok": True, "answer": answer, "hit": hit,
                                "fallback": fallback, "logged": logged,
                                "saved": "_wiki/under_review/" if hit else ""})

    # ---- 静态托管(白名单 + 防穿越)----
    def _static(self, path):
        rel = unquote(path).lstrip("/")
        if not rel or rel.split("/", 1)[0] not in STATIC_ROOTS:
            return self._json(404, {"ok": False, "error": "not found"})
        target = (VAULT / rel).resolve()
        allowed = any(target.is_relative_to((VAULT / r).resolve()) for r in STATIC_ROOTS)
        if not allowed:
            return self._json(403, {"ok": False, "error": "forbidden"})
        if target.is_dir():
            target = target / "index.html"
        return self._serve_file(target)

    def _serve_file(self, target: Path):
        if not target.is_file():
            return self._json(404, {"ok": False, "error": "not found"})
        ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript",):
            ctype += "; charset=utf-8"
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    ap = argparse.ArgumentParser(description="第二大脑本地服务(静态 browse/ + 引擎查询 API)")
    ap.add_argument("--port", type=int, default=8788)
    args = ap.parse_args()
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"🧠 brain-server @ http://127.0.0.1:{args.port}/  (入口=/browse/index.html,Ctrl-C 停)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
