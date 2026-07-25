"""brain-server 的行为测试:browse_stale() 的健壮性 + /api/query 的 eval 流量不记账。
文件名带连字符,用 importlib 按路径装载(与 test_build_subscriptions_site 同法)。
"""
import importlib.util
import json
import stat
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _load():
    spec = importlib.util.spec_from_file_location("brain_server", REPO / "scripts" / "brain-server.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# ---------- browse_stale ----------

def test_browse_stale_none_without_manifest(tmp_path, monkeypatch):
    m = _load()
    monkeypatch.setattr(m, "VAULT", tmp_path)
    assert m.browse_stale() is None       # 未构建 → 无从判断


def test_browse_stale_false_when_fresh_true_when_changed(tmp_path, monkeypatch):
    m = _load()
    monkeypatch.setattr(m, "VAULT", tmp_path)
    page = tmp_path / "_wiki" / "concepts" / "页.md"
    page.parent.mkdir(parents=True)
    page.write_text("v1", encoding="utf-8")

    import indexlib
    fp = indexlib.input_fingerprint(indexlib.browse_inputs(tmp_path), base=tmp_path)
    manifest = tmp_path / "browse" / "wiki" / ".build-manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({"schema_version": indexlib.MANIFEST_SCHEMA,
                                    "fingerprint": fp["fingerprint"]}), encoding="utf-8")
    assert m.browse_stale() is False
    page.write_text("v2", encoding="utf-8")
    assert m.browse_stale() is True


def test_browse_stale_survives_non_dict_manifest(tmp_path, monkeypatch):
    # 评审 PLAUSIBLE:manifest 是合法 JSON 但非对象(如数组)→ 不得 500,应返回 None
    m = _load()
    monkeypatch.setattr(m, "VAULT", tmp_path)
    manifest = tmp_path / "browse" / "wiki" / ".build-manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text("[1, 2, 3]", encoding="utf-8")
    assert m.browse_stale() is None


# ---------- /api/query 的 eval 流量 ----------

def _serve(m):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), m.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def _post(port, payload):
    req = urllib.request.Request(f"http://127.0.0.1:{port}/api/query",
                                 data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def test_api_search_ranked_results_and_auto_refresh(tmp_path, monkeypatch):
    # P1-1:/api/search 秒级本地检索(不走 LLM),内容变化后自动刷新
    m = _load()
    monkeypatch.setattr(m, "VAULT", tmp_path)
    page = tmp_path / "_wiki" / "concepts" / "知识复利.md"
    page.parent.mkdir(parents=True)
    page.write_text("知识复利:每次摄入都让库增值,持续保鲜。", encoding="utf-8")

    srv = _serve(m)
    try:
        port = srv.server_address[1]
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/search",
                                     data=json.dumps({"q": "知识 增值"}).encode("utf-8"),
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            r = json.loads(resp.read().decode("utf-8"))
        assert r["ok"] is True and r["results"]
        assert r["results"][0]["path"].endswith("知识复利.md")

        # 新增页面后再搜:应能搜到(索引自动刷新)
        page2 = tmp_path / "_wiki" / "outputs" / "评测基线.md"
        page2.parent.mkdir(parents=True)
        page2.write_text("评测基线:golden case 回归。", encoding="utf-8")
        req2 = urllib.request.Request(f"http://127.0.0.1:{port}/api/search",
                                      data=json.dumps({"q": "评测 基线"}).encode("utf-8"),
                                      headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req2, timeout=10) as resp:
            r2 = json.loads(resp.read().decode("utf-8"))
        assert r2["results"] and r2["results"][0]["path"].endswith("评测基线.md")
    finally:
        srv.shutdown()


def test_query_fallback_requery_includes_synonyms(tmp_path, monkeypatch):
    # P1-1:引擎首查无命中 → 兜底重查的查询串应包含同义扩展词(冲突→conflict)
    m = _load()
    flag = tmp_path / "called_once"
    stub = tmp_path / "sage-wiki"
    stub.write_text(
        "#!/bin/sh\n"
        f"if [ -f '{flag}' ]; then echo \"REQUERY:$2\"; else touch '{flag}'; "
        "echo 'No relevant articles found'; fi\n", encoding="utf-8")
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setattr(m, "find_sage", lambda: str(stub))
    monkeypatch.setattr(m, "append_query_log", lambda q: True)

    srv = _serve(m)
    try:
        r = _post(srv.server_address[1], {"q": "冲突的知识页有哪些", "eval": True})
        assert r["fallback"] is True, r
        assert "conflict" in r["answer"], f"兜底重查应含同义扩展词:{r['answer']}"
    finally:
        srv.shutdown()


# ---------- /api/update-all + /api/update-status(网页一键全量更新)----------

def _get(port, path):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


def _post_to(port, path, headers=None):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=b"",
                                 headers=headers or {}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


def _stub(tmp_path, body):
    s = tmp_path / "update-stub.sh"
    s.write_text("#!/bin/sh\n" + body + "\n", encoding="utf-8")
    s.chmod(s.stat().st_mode | stat.S_IEXEC)
    return str(s)


def _wait_done(port, timeout=10):
    t0 = time.time()
    while time.time() - t0 < timeout:
        st = _get(port, "/api/update-status")
        if not st["running"]:
            return st
        time.sleep(0.03)
    raise AssertionError("update-all 未在超时内结束")


def test_update_status_idle_shape(tmp_path, monkeypatch):
    m = _load()
    monkeypatch.setattr(m, "VAULT", tmp_path)
    srv = _serve(m)
    try:
        st = _get(srv.server_address[1], "/api/update-status")
        assert st["running"] is False and st["returncode"] is None and st["log"] == ""
    finally:
        srv.shutdown()


def test_update_all_starts_runs_and_reports(tmp_path, monkeypatch):
    m = _load()
    monkeypatch.setattr(m, "VAULT", tmp_path)
    monkeypatch.setenv("MIND_UPDATE_SCRIPT", _stub(tmp_path, "echo HELLO-UPDATE; exit 0"))
    srv = _serve(m)
    try:
        port = srv.server_address[1]
        code, j = _post_to(port, "/api/update-all")
        assert code == 200 and j["status"] == "started", j
        st = _wait_done(port)
        assert st["returncode"] == 0, st
        assert "HELLO-UPDATE" in st["log"], st["log"]
        # 输出确实落到 browse/.update-all.log
        assert (tmp_path / "browse" / ".update-all.log").exists()
    finally:
        srv.shutdown()


def test_update_all_single_flight(tmp_path, monkeypatch):
    m = _load()
    monkeypatch.setattr(m, "VAULT", tmp_path)
    monkeypatch.setenv("MIND_UPDATE_SCRIPT", _stub(tmp_path, "sleep 0.6; exit 0"))
    srv = _serve(m)
    try:
        port = srv.server_address[1]
        _, j1 = _post_to(port, "/api/update-all")
        _, j2 = _post_to(port, "/api/update-all")
        assert j1["status"] == "started" and j2["status"] == "running", (j1, j2)
        _wait_done(port)
    finally:
        srv.shutdown()


def test_update_all_failure_returncode_surfaced(tmp_path, monkeypatch):
    m = _load()
    monkeypatch.setattr(m, "VAULT", tmp_path)
    monkeypatch.setenv("MIND_UPDATE_SCRIPT", _stub(tmp_path, "echo boom; exit 3"))
    srv = _serve(m)
    try:
        port = srv.server_address[1]
        _post_to(port, "/api/update-all")
        assert _wait_done(port)["returncode"] == 3
    finally:
        srv.shutdown()


def test_update_all_origin_guard(tmp_path, monkeypatch):
    # 跨站来源(恶意网页)不得触发本机重建;file:// 的 null 来源放行
    m = _load()
    monkeypatch.setattr(m, "VAULT", tmp_path)
    monkeypatch.setenv("MIND_UPDATE_SCRIPT", _stub(tmp_path, "exit 0"))
    srv = _serve(m)
    try:
        port = srv.server_address[1]
        code, _ = _post_to(port, "/api/update-all", headers={"Origin": "http://evil.example"})
        assert code == 403, code
        assert _get(port, "/api/update-status")["running"] is False, "跨站请求不得启动"
        code2, j2 = _post_to(port, "/api/update-all", headers={"Origin": "null"})
        assert code2 == 200 and j2["status"] == "started"
        _wait_done(port)
    finally:
        srv.shutdown()


def test_eval_traffic_not_logged(tmp_path, monkeypatch):
    # 评审确认问题:评测流量污染调用记账。带 eval:true 的请求不得调用 append_query_log。
    m = _load()
    stub = tmp_path / "sage-wiki"
    stub.write_text("#!/bin/sh\necho '答案:知识复利页说……'\n", encoding="utf-8")
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setattr(m, "find_sage", lambda: str(stub))
    logged_calls = []
    monkeypatch.setattr(m, "append_query_log", lambda q: logged_calls.append(q) or True)

    srv = _serve(m)
    try:
        r1 = _post(srv.server_address[1], {"q": "知识复利", "eval": True})
        assert r1["ok"] is True and r1["hit"] is True
        assert r1["logged"] is False
        assert logged_calls == [], "eval 流量不得记账"

        r2 = _post(srv.server_address[1], {"q": "知识复利"})
        assert r2["logged"] is True
        assert logged_calls == ["知识复利"], "正常流量仍应记账"
    finally:
        srv.shutdown()
