"""decision.py 决策队列状态机的行为测试(P1-2,FR-SCH-06)。
契约:
- new:在 <vault>/_wiki/outputs/decisions/ 建 DEC-YYYYMMDD-NN 记录(pending,四节骨架);同日 ID 递增。
- 状态机:pending→approved|rejected|deferred;deferred→approved|rejected;approved→applied。
  非法迁移(如 apply 一个 pending)必须报错非零退出,文件不被改动。
- **approved 只是授权**:approve 盖 decided_at;apply 才盖 applied_at(审批与执行分离)。
- check:校验全部记录的不变量,违规非零退出(供 lint 接入)。
- board:幂等生成唯一用户入口页(Dataview 聚合)。
全部经 subprocess 跑 CLI,--vault 指向 tmp 目录,不碰真实仓库。
"""
import json
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CLI = REPO / "scripts" / "decision.py"


def _run(vault: Path, *args):
    return subprocess.run(["python3", str(CLI), *args, "--vault", str(vault)],
                          capture_output=True, text=True, cwd=str(REPO))


def _records_dir(vault: Path) -> Path:
    return vault / "_wiki" / "outputs" / "decisions"


def _new(vault: Path, title="提升某查询产出入库", typ="promote"):
    r = _run(vault, "new", typ, title, "--target", "_wiki/under_review/某产物.md")
    assert r.returncode == 0, r.stdout + r.stderr
    m = re.search(r"DEC-\d{8}-\d{2,}", r.stdout)
    assert m, "new 应打印生成的 decision_id:" + r.stdout
    return m.group(0)


def test_new_creates_pending_record_with_skeleton(tmp_path):
    did = _new(tmp_path)
    files = list(_records_dir(tmp_path).glob("*.md"))
    assert len(files) == 1
    text = files[0].read_text(encoding="utf-8")
    assert f"decision_id: {did}" in text
    assert "decision_status: pending" in text
    assert "decision_type: promote" in text
    assert "target: _wiki/under_review/某产物.md" in text
    for sec in ("## 需要决定", "## 建议及依据", "## 可选项与影响", "## 用户决策"):
        assert sec in text, f"缺少骨架小节 {sec}"


def test_new_ids_increment_same_day(tmp_path):
    a = _new(tmp_path, title="第一件")
    b = _new(tmp_path, title="第二件")
    assert a != b
    assert int(b[-2:]) == int(a[-2:]) + 1


def test_approve_sets_decided_at_but_not_applied(tmp_path):
    did = _new(tmp_path)
    r = _run(tmp_path, "approve", did, "--note", "同意提升")
    assert r.returncode == 0, r.stdout + r.stderr
    text = next(_records_dir(tmp_path).glob("*.md")).read_text(encoding="utf-8")
    assert "decision_status: approved" in text
    assert re.search(r"decided_at: \d{4}-\d{2}-\d{2}", text)
    assert "applied_at:" not in text, "approve 不得盖 applied_at(审批≠执行)"
    assert "同意提升" in text


def test_apply_requires_approved(tmp_path):
    did = _new(tmp_path)
    r = _run(tmp_path, "apply", did)                       # pending 直接 apply → 拒绝
    assert r.returncode != 0, "pending 不得直接 apply"
    text = next(_records_dir(tmp_path).glob("*.md")).read_text(encoding="utf-8")
    assert "decision_status: pending" in text, "非法迁移不得改动文件"

    _run(tmp_path, "approve", did)
    r2 = _run(tmp_path, "apply", did)
    assert r2.returncode == 0, r2.stdout + r2.stderr
    text2 = next(_records_dir(tmp_path).glob("*.md")).read_text(encoding="utf-8")
    assert "decision_status: applied" in text2
    assert re.search(r"applied_at: \d{4}-\d{2}-\d{2}", text2)


def test_reject_and_defer_transitions(tmp_path):
    a = _new(tmp_path, title="要拒的")
    b = _new(tmp_path, title="要缓的")
    assert _run(tmp_path, "reject", a).returncode == 0
    assert _run(tmp_path, "defer", b).returncode == 0
    assert _run(tmp_path, "approve", b).returncode == 0    # deferred → approved 合法
    assert _run(tmp_path, "approve", a).returncode != 0    # rejected 是终态


def test_list_filters_by_status(tmp_path):
    a = _new(tmp_path, title="甲")
    b = _new(tmp_path, title="乙")
    _run(tmp_path, "approve", a)
    r = _run(tmp_path, "list", "--status", "pending", "--json")
    out = json.loads(r.stdout)
    ids = [x["decision_id"] for x in out]
    assert b in ids and a not in ids


def test_check_catches_invariant_violations(tmp_path):
    did = _new(tmp_path)
    assert _run(tmp_path, "check").returncode == 0         # 健康库 check 过
    # 手工制造违规:approved 却没有 decided_at
    f = next(_records_dir(tmp_path).glob("*.md"))
    f.write_text(f.read_text(encoding="utf-8").replace(
        "decision_status: pending", "decision_status: approved"), encoding="utf-8")
    r = _run(tmp_path, "check")
    assert r.returncode != 0, "approved 无 decided_at 应被 check 抓住"
    assert did in (r.stdout + r.stderr)


def test_approve_note_with_backslash_and_regex_meta(tmp_path):
    # 评审 HIGH:note 进 re.sub replacement 位 → 反斜杠崩溃 / \g<0> 静默注入
    did = _new(tmp_path)
    r = _run(tmp_path, "approve", did, "--note", r"备份在 C:\Users\shuo,见方案\1与\g<0>")
    assert r.returncode == 0, "note 含反斜杠/正则元字符不得崩溃:" + r.stdout + r.stderr
    text = next(_records_dir(tmp_path).glob("*.md")).read_text(encoding="utf-8")
    assert r"C:\Users\shuo" in text, "反斜杠应原样保留"
    assert "decision_status: approvedy" not in text and r"\g<0>" in text, "不得发生 replacement 注入"


def test_title_with_colon_written_yaml_safe(tmp_path):
    # 评审 HIGH:标题含「: 」裸拼 frontmatter 不是合法 YAML → Dataview 解析失败,
    # 记录在唯一用户入口看板上静默隐身。含冒号的值必须引号化。
    r = _run(tmp_path, "new", "promote", "P1-2: 决策队列上线", "--target", "_wiki/x.md")
    assert r.returncode == 0, r.stdout + r.stderr
    text = next(_records_dir(tmp_path).glob("*.md")).read_text(encoding="utf-8")
    assert 'title: "P1-2: 决策队列上线"' in text, "含冒号的 title 必须 YAML 引号化:\n" + text
    # 且本脚本自己的 parse 能读回去(list 不显示引号)
    r2 = _run(tmp_path, "list", "--json")
    out = json.loads(r2.stdout)
    assert out[0]["title"] == "P1-2: 决策队列上线"


def test_newline_in_values_rejected(tmp_path):
    # 评审 MEDIUM:值含换行 → frontmatter 行注入(伪造 decision_status)。入口拒绝。
    r = _run(tmp_path, "new", "promote", "看似正常\ndecision_status: approved")
    assert r.returncode == 2, "含换行的 title 应按用法错误拒绝"
    did = _new(tmp_path)
    r2 = _run(tmp_path, "approve", did, "--note", "第一行\n第二行")
    assert r2.returncode == 2, "含换行的 note 应拒绝"


def test_set_fm_only_touches_frontmatter_block(tmp_path):
    # 评审 MEDIUM:--recommend 正文里出现「applied_at: …」字样时,
    # approve/apply 必须改 frontmatter 而不是误改正文
    r = _run(tmp_path, "new", "promote", "带干扰的记录",
             "--recommend", "applied_at: 手工填写执行日(评审复现:正文行首出现字段名)")
    assert r.returncode == 0
    m = re.search(r"DEC-\d{8}-\d{2,}", r.stdout)
    did = m.group(0)
    _run(tmp_path, "approve", did)
    assert _run(tmp_path, "apply", did).returncode == 0
    text = next(_records_dir(tmp_path).glob("*.md")).read_text(encoding="utf-8")
    fm = text.split("---\n")[1]
    assert re.search(r"(?m)^applied_at: \d{4}-", fm), "applied_at 必须落在 frontmatter"
    assert "applied_at: 手工填写执行日" in text, "正文原文不得被误改"


def test_list_survives_foreign_files_and_bom(tmp_path):
    # 评审 MEDIUM:decisions/ 下的 README/带 BOM 文件不得让 list 崩溃,BOM 记录不得导致 ID 复用
    a = _new(tmp_path)
    d = _records_dir(tmp_path)
    (d / "README.md").write_text("说明文件,无 frontmatter", encoding="utf-8")
    # 给现有记录加 BOM(模拟 Windows 编辑器)
    f = next(d.glob("DEC-*.md"))
    f.write_bytes(b"\xef\xbb\xbf" + f.read_bytes())
    r = _run(tmp_path, "list")
    assert r.returncode == 0, "坏文件不得让 list 崩溃:" + r.stdout + r.stderr
    b = _new(tmp_path, title="第二件")
    assert b != a, "BOM 不得导致 decision_id 复用"


def test_seq_beyond_99_stays_unique(tmp_path):
    # 评审 LOW:同日第 100 条起 ID 恒重复(取 [-2:] 截断)。用 fixture 直接铺一条 99 号验证。
    d = _records_dir(tmp_path)
    d.mkdir(parents=True)
    from datetime import date
    today = date.today().strftime("%Y%m%d")
    (d / f"DEC-{today}-99-老记录.md").write_text(
        f"---\ntitle: 老\ndecision_id: DEC-{today}-99\ndecision_type: other\n"
        f"decision_status: pending\ncreated: x\n---\n", encoding="utf-8")
    new_id = _new(tmp_path, title="第一百件")
    assert new_id == f"DEC-{today}-100"
    assert _run(tmp_path, "check").returncode == 0, "三位序号应是合法 ID"


def test_reject_records_reason(tmp_path):
    # 评审:拒绝理由无处可记 → reject 也支持 --note
    did = _new(tmp_path)
    r = _run(tmp_path, "reject", did, "--note", "与现有页重复,不提升")
    assert r.returncode == 0, r.stdout + r.stderr
    text = next(_records_dir(tmp_path).glob("*.md")).read_text(encoding="utf-8")
    assert "与现有页重复,不提升" in text


def test_check_catches_deferred_with_decided_and_bad_type(tmp_path):
    # 评审:check 漏网——deferred 带 decided_at、非法 decision_type
    did = _new(tmp_path)
    f = next(_records_dir(tmp_path).glob("*.md"))
    t = f.read_text(encoding="utf-8")
    t = t.replace("decision_status: pending", "decision_status: deferred\ndecided_at: 2026-07-23")
    t = t.replace("decision_type: promote", "decision_type: banana")
    f.write_text(t, encoding="utf-8")
    r = _run(tmp_path, "check")
    assert r.returncode != 0
    err = r.stdout + r.stderr
    assert "deferred" in err and "banana" in err


def test_board_preserves_user_edits(tmp_path):
    # 评审:看板是"唯一用户入口",用户手工批注不得被 board 静默覆盖
    _run(tmp_path, "board")
    page = tmp_path / "_wiki" / "outputs" / "待确认看板.md"
    edited = page.read_text(encoding="utf-8") + "\n## 我的手记\n重要批注\n"
    page.write_text(edited, encoding="utf-8")
    assert _run(tmp_path, "board").returncode == 0
    assert "重要批注" in page.read_text(encoding="utf-8"), "用户编辑不得被覆盖"


def test_board_idempotent_single_entry(tmp_path):
    _new(tmp_path)
    assert _run(tmp_path, "board").returncode == 0
    page = tmp_path / "_wiki" / "outputs" / "待确认看板.md"
    assert page.exists()
    first = page.read_text(encoding="utf-8")
    assert "dataview" in first and "decisions" in first
    assert _run(tmp_path, "board").returncode == 0          # 再跑一次:幂等
    assert page.read_text(encoding="utf-8") == first
