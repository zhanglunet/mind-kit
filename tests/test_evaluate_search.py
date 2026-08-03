"""evaluate_search.py 的行为测试(P0-1b):检索回归 runner。
fixture 后端:内嵌语料 + 参考打分器,断言 expected_top1/expected_in_top3/forbidden_top1/
expect_no_results 并计算 MRR;brain 后端:POST /api/query,断言 expected_cite/forbidden_cite。
"""
import sys
import json
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RUNNER = REPO / "scripts" / "evaluate_search.py"


def _run(*args):
    return subprocess.run([sys.executable, str(RUNNER), *args],
                          capture_output=True, text=True, cwd=str(REPO))


def _case_file(tmp_path: Path, corpus, cases) -> Path:
    p = tmp_path / "cases.json"
    p.write_text(json.dumps(
        {"schema_version": "eval-retrieval-1", "corpus": corpus, "cases": cases},
        ensure_ascii=False), encoding="utf-8")
    return p


CORPUS = [
    {"path": "_wiki/concepts/知识复利.md", "title": "知识复利",
     "content": "知识复利指每次摄入与查询都让知识库增值,编译一次持续保鲜。"},
    {"path": "_wiki/concepts/复利陷阱.md", "title": "复利陷阱",
     "content": "复利陷阱是干扰项:讲金融投资里的复利风险,与知识管理无关。"},
    {"path": "_wiki/outputs/检索评测.md", "title": "检索评测",
     "content": "retrieval evaluation 用 golden cases 计算 MRR 与 Top-1 命中率。"},
]


def test_expected_top1_and_mrr_pass(tmp_path):
    f = _case_file(tmp_path, CORPUS, [
        {"id": "t1", "query": "知识库 增值 保鲜", "expected_top1": "_wiki/concepts/知识复利.md"},
        {"id": "t2", "query": "golden cases MRR", "expected_top1": "_wiki/outputs/检索评测.md"},
    ])
    r = _run(str(f), "--json")
    assert r.returncode == 0, r.stdout + r.stderr
    out = json.loads(r.stdout)
    assert out["passed"] == 2 and out["failed"] == 0
    assert out["mrr"] == 1.0


def test_wrong_expected_top1_fails(tmp_path):
    f = _case_file(tmp_path, CORPUS, [
        {"id": "t1", "query": "知识库 增值 保鲜", "expected_top1": "_wiki/concepts/复利陷阱.md"},
    ])
    r = _run(str(f), "--json")
    assert r.returncode == 1  # 有 case 失败 → 非零退出


def test_forbidden_top1_distractor(tmp_path):
    # 干扰分离:问知识管理复利,金融干扰页不得排第一
    f = _case_file(tmp_path, CORPUS, [
        {"id": "d1", "query": "知识 复利 保鲜",
         "forbidden_top1": "_wiki/concepts/复利陷阱.md"},
    ])
    r = _run(str(f), "--json")
    assert r.returncode == 0, r.stdout + r.stderr


def test_expect_no_results_for_fabricated_entity(tmp_path):
    f = _case_file(tmp_path, CORPUS, [
        {"id": "n1", "query": "量子海鲜反应堆 ZX-99 部署手册", "expect_no_results": True},
    ])
    r = _run(str(f), "--json")
    assert r.returncode == 0, r.stdout + r.stderr


def test_cjk_bigram_matches_long_chinese_query(tmp_path):
    # 整句长中文(无空格)也要能命中 —— 参考打分器需做 CJK bigram
    f = _case_file(tmp_path, CORPUS, [
        {"id": "c1", "query": "怎样让知识库持续保鲜增值",
         "expected_top1": "_wiki/concepts/知识复利.md"},
    ])
    r = _run(str(f), "--json")
    assert r.returncode == 0, r.stdout + r.stderr


def test_committed_smoke_fixture_passes():
    # 入库的冒烟 fixture 必须全绿 —— 这是接进 pytest/pre-push/CI 的基线本体。
    # 条数锁定为 fixture 实际条数且 ≥8:静默删 case 会红(基线只增不减的机检)。
    fixture = REPO / "evaluation" / "fixtures" / "retrieval_smoke.json"
    assert fixture.exists(), "evaluation/fixtures/retrieval_smoke.json 应存在"
    n_cases = len(json.loads(fixture.read_text(encoding="utf-8"))["cases"])
    assert n_cases >= 8, "冒烟基线只增不减(当前 8 条)"
    r = _run(str(fixture), "--json")
    assert r.returncode == 0, r.stdout + r.stderr
    out = json.loads(r.stdout)
    assert out["failed"] == 0 and out["total"] == n_cases
    assert out["mrr"] >= 0.75


def test_zero_cases_is_usage_error(tmp_path):
    # cases 为空/键拼错 → 不得静默绿灯,应 exit 2
    f = _case_file(tmp_path, CORPUS, [])
    r = _run(str(f), "--json")
    assert r.returncode == 2, f"0 个 case 应 exit 2,实际 {r.returncode}"


def test_local_backend_passes_smoke_fixture():
    # P1-1 不回退门禁:新检索栈(searchlib)必须全过旧冒烟基线
    fixture = REPO / "evaluation" / "fixtures" / "retrieval_smoke.json"
    r = _run(str(fixture), "--backend", "local", "--json")
    assert r.returncode == 0, r.stdout + r.stderr
    out = json.loads(r.stdout)
    assert out["failed"] == 0 and out["mrr"] >= 0.75


def test_local_backend_passes_hard_fixture_old_scorer_fails_some():
    # P1-1 量化提升门禁:难 fixture 上,新栈全过;旧参考打分器必须至少败一条
    # (否则"升级"没有可测量的提升,不该合并——FR-QRY-06)
    hard = REPO / "evaluation" / "fixtures" / "retrieval_hard.json"
    assert hard.exists(), "evaluation/fixtures/retrieval_hard.json 应存在"
    r_new = _run(str(hard), "--backend", "local", "--json")
    assert r_new.returncode == 0, "新检索栈应全过难 fixture:" + r_new.stdout + r_new.stderr
    out_new = json.loads(r_new.stdout)
    assert out_new["failed"] == 0 and out_new["total"] >= 4

    r_old = _run(str(hard), "--backend", "fixture", "--json")
    assert r_old.returncode == 1, "旧参考打分器应至少败一条难 case(证明提升可测量)"
    out_old = json.loads(r_old.stdout)
    # 评审加固:锁定"旧败"的精确集合(h1/h2/h3 双语同义类),防语料微调后叙事漂移而测试仍绿
    failed_ids = {r["id"] for r in out_old["results"] if not r["ok"]}
    assert {"h1-中文查英文页", "h2-纯英查中文页", "h3-同义词跨语言"} <= failed_ids, failed_ids


def test_local_backend_empty_vault_is_usage_error(tmp_path):
    # 评审确认问题:local 后端 + 无 corpus + vault 目录缺失 → 空索引静默评测可假绿。
    # 新契约:--vault 指向的输入面为空时按用法错误 exit 2。
    f = _case_file(tmp_path, [], [
        {"id": "n1", "query": "任意查询", "expect_no_results": True},
    ])
    # 内嵌 corpus 为空列表 → 走 vault 索引;指向空目录必须拒绝评测
    r = _run(str(f), "--backend", "local", "--vault", str(tmp_path / "empty-vault"), "--json")
    assert r.returncode == 2, f"空输入面应 exit 2(拒绝假绿),实际 {r.returncode}:{r.stdout}{r.stderr}"
    assert "为空" in (r.stdout + r.stderr), "应明确提示输入面为空,而非 argparse 用法错误:" + r.stderr


def test_multi_assertion_case_is_config_error(tmp_path):
    # 一个 case 同时写多个断言字段 → 不得静默取其一,应判该 case 配置错误
    f = _case_file(tmp_path, CORPUS, [
        {"id": "x1", "query": "知识 复利",
         "expected_top1": "_wiki/concepts/知识复利.md",
         "forbidden_top1": "_wiki/concepts/复利陷阱.md"},
    ])
    r = _run(str(f), "--json")
    assert r.returncode == 1
    out = json.loads(r.stdout)
    assert "断言" in out["results"][0]["detail"]


def test_mrr_below_threshold_explained_in_text_mode(tmp_path):
    # 全 case 过但 MRR 低于门槛 → exit 1,且文本输出必须解释原因(不只藏在 JSON)
    f = _case_file(tmp_path, CORPUS, [
        # 期望页排第 2(干扰页信号更强):expected_in_top3 通过,但 rr=0.5 → MRR 0.5 < 0.75
        {"id": "r2", "query": "金融 投资 复利 风险 保鲜",
         "expected_in_top3": "_wiki/concepts/知识复利.md"},
    ])
    r = _run(str(f))
    if r.returncode == 1:  # 排名如预期(第 2 位)时,必须给出人话解释
        assert "MRR" in r.stdout and ("门槛" in r.stdout or "<" in r.stdout), r.stdout


def test_brain_backend_bad_json_response_no_crash(tmp_path):
    class _BadStub(BaseHTTPRequestHandler):
        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            self.rfile.read(n)
            data = b"<html>not json</html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, fmt, *args):
            pass

    srv = HTTPServer(("127.0.0.1", 0), _BadStub)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        f = _case_file(tmp_path, [], [
            {"id": "b1", "query": "任意问题", "expected_cite": "任意"},
        ])
        r = _run(str(f), "--backend", "brain", "--port", str(srv.server_address[1]), "--json")
        assert r.returncode == 1, "坏响应应判该 case 失败而非崩溃"
        out = json.loads(r.stdout)          # 报告必须仍是合法 JSON
        assert out["results"][0]["ok"] is False
    finally:
        srv.shutdown()


_SEEN_PAYLOADS = []


class _RecordingStub(BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        payload = json.loads(self.rfile.read(n))
        _SEEN_PAYLOADS.append(payload)
        body = {"ok": True, "hit": True, "answer": "引用〔知识复利〕"}
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        pass


def test_brain_backend_marks_eval_traffic(tmp_path):
    # 评审确认问题:评测流量会污染生产调用记账 → runner 必须在请求里声明 eval:true
    _SEEN_PAYLOADS.clear()
    srv = HTTPServer(("127.0.0.1", 0), _RecordingStub)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        f = _case_file(tmp_path, [], [
            {"id": "e1", "query": "知识复利", "expected_cite": "知识复利"},
        ])
        r = _run(str(f), "--backend", "brain", "--port", str(srv.server_address[1]), "--json")
        assert r.returncode == 0, r.stdout + r.stderr
        assert _SEEN_PAYLOADS and all(p.get("eval") is True for p in _SEEN_PAYLOADS), \
            f"评测请求必须带 eval:true,实际 {_SEEN_PAYLOADS}"
    finally:
        srv.shutdown()


class _StubBrain(BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        q = json.loads(self.rfile.read(n))["q"]
        if "无中生有" in q:
            body = {"ok": True, "answer": "（未找到相关内容）", "hit": False}
        else:
            body = {"ok": True, "hit": True,
                    "answer": "根据〔知识复利〕页:每次摄入都让库增值。来源:_wiki/concepts/知识复利.md"}
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        pass


def test_brain_backend_cite_assertions(tmp_path):
    srv = HTTPServer(("127.0.0.1", 0), _StubBrain)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        f = _case_file(tmp_path, [], [
            {"id": "b1", "query": "知识复利是什么", "expected_cite": "知识复利"},
            {"id": "b2", "query": "知识复利是什么", "forbidden_cite": "复利陷阱"},
            {"id": "b3", "query": "无中生有实体查询", "expect_no_results": True},
        ])
        r = _run(str(f), "--backend", "brain", "--port", str(srv.server_address[1]), "--json")
        assert r.returncode == 0, r.stdout + r.stderr
        out = json.loads(r.stdout)
        assert out["passed"] == 3
    finally:
        srv.shutdown()
