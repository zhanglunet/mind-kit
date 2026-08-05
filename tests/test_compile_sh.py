"""compile.sh 的失败可见性(2026-08-04 对抗核验翻出的第 ④ 条)。

契约:
- **能做的做完,但如实报失败**。第 3 步建索引、第 4 步 lint 挂掉时,不中止
  (中止会丢掉本轮编译产物——第 6 步才提交),但**末尾必须非零退出**。
- 原先这两步既无 `||` 兜底也无退出码检查:build-index 挂掉只打一行 traceback,
  流水线照走到 `✔ 流水线完成` 退 0,**索引悄悄停在上一轮版本**。
- **记账类步骤仍是 best-effort**:freshness / decision check / okf --check 报出
  「有待补页」「有违规」是**内容发现**,不是基础设施故障,不该让整轮判失败。
  这条区分是刻意的,一并钉住。

测试一律在**合成仓**里跑(拷脚本 + 打桩),绝不碰真实知识库。
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

STUB_OK = "#!/usr/bin/env python3\nimport sys\nsys.exit(0)\n"
STUB_FAIL = "#!/usr/bin/env python3\nimport sys\nprint('boom', file=sys.stderr)\nsys.exit(1)\n"


def _repo(tmp_path, *, sage_lint_rc=0, sage_lint_out="lint: 0 findings",
          build_index_ok=True, accounting_ok=True):
    """合成仓:真 compile.sh + 全套打桩。返回 (仓库路径, PATH)。"""
    v = tmp_path / "mind"
    (v / "scripts").mkdir(parents=True)
    (v / "_wiki").mkdir()
    for f in ("compile.sh", "_pyresolve.sh"):
        shutil.copy(REPO / "scripts" / f, v / "scripts" / f)

    py = STUB_OK if build_index_ok else STUB_FAIL
    (v / "scripts" / "build-index.py").write_text(py, encoding="utf-8")
    acc = STUB_OK if accounting_ok else STUB_FAIL
    for name in ("okf.py", "freshness.py", "decision.py", "build-wiki-site.py"):
        (v / "scripts" / name).write_text(acc if name != "build-wiki-site.py" else STUB_OK,
                                          encoding="utf-8")
    # vault.sh 留痕,用来验证「被拦下时产物仍然提交了」
    (v / "scripts" / "vault.sh").write_text(
        '#!/usr/bin/env bash\necho "COMMITTED:$*" >> "$(dirname "$0")/../.commit-log"\nexit 0\n',
        encoding="utf-8")

    # sage-wiki 桩:compile 恒成功;lint 的退出码与输出可控
    bind = tmp_path / "bin"
    bind.mkdir()
    (bind / "sage-wiki").write_text(
        f'#!/usr/bin/env bash\n'
        f'case "$1" in\n'
        f'  compile) exit 0 ;;\n'
        f'  lint) printf "%s\\n" {sage_lint_out!r}; exit {sage_lint_rc} ;;\n'
        f'esac\nexit 0\n', encoding="utf-8")
    (bind / "sage-wiki").chmod(0o755)
    return v, f"{bind}{os.pathsep}{os.environ.get('PATH','')}"


def _run(v, path, tmp_path):
    env = {**os.environ, "PATH": path, "HOME": str(tmp_path),
           "MIND_PYTHON": sys.executable}
    return subprocess.run(["bash", str(v / "scripts" / "compile.sh")],
                          cwd=str(v), capture_output=True, text=True, env=env, timeout=120)


def _committed(v):
    f = v / ".commit-log"
    return f.read_text(encoding="utf-8") if f.exists() else ""


def test_all_green_exits_zero(tmp_path):
    v, path = _repo(tmp_path)
    r = _run(v, path, tmp_path)
    assert r.returncode == 0, (r.stdout + r.stderr)[-600:]
    assert "流水线完成" in r.stdout
    assert "COMMITTED" in _committed(v)


def test_build_index_failure_makes_pipeline_exit_nonzero(tmp_path):
    """建索引挂掉:**不中止**(产物还要提交),但末尾必须非零退出。

    原先它连退出码都不看 —— traceback 一闪而过,最后照样打 `✔ 流水线完成` 退 0,
    索引悄悄停在上一轮版本,而 cron 天天报绿。
    """
    v, path = _repo(tmp_path, build_index_ok=False)
    r = _run(v, path, tmp_path)
    out = r.stdout + r.stderr
    assert r.returncode != 0, "建索引失败必须让整轮非零退出:" + out[-700:]
    assert "index" in out or "索引" in out, "要说清是哪一步失败:" + out[-700:]
    assert "COMMITTED" in _committed(v), \
        "不许因此丢掉本轮编译产物 —— 提交步仍须执行"


def test_lint_failure_makes_pipeline_exit_nonzero(tmp_path):
    """引擎 lint 挂掉同样要非零退出(而不是靠 tee 把退出码吃掉)。"""
    v, path = _repo(tmp_path, sage_lint_rc=1)
    r = _run(v, path, tmp_path)
    out = r.stdout + r.stderr
    assert r.returncode != 0, "lint 失败必须让整轮非零退出:" + out[-700:]
    assert "lint" in out
    assert "COMMITTED" in _committed(v), "产物仍须提交"


def test_lint_success_not_confused_by_grep_filtering_everything(tmp_path):
    """**最容易写错的一处**:lint 成功但输出全被 grep 过滤掉时,不许误判成失败。

    第 4 步是 `sage-wiki lint | grep -v … | tee`。`grep -v` 在一行都不剩时返回 1,
    加上 `set -o pipefail`,整条管线的退出码就是 1 —— 但引擎其实是成功的。
    所以必须只看 `PIPESTATUS[0]`(引擎自己的退出码),不能看整条管线。
    """
    v, path = _repo(tmp_path, sage_lint_rc=0,
                    sage_lint_out="time=xxx embedding disabled")  # 恰好会被 grep -v 滤掉
    r = _run(v, path, tmp_path)
    assert r.returncode == 0, \
        "引擎成功、只是输出被过滤干净,不该判失败:" + (r.stdout + r.stderr)[-700:]


def test_accounting_steps_stay_best_effort(tmp_path):
    """记账类步骤(保鲜 / 决策不变量 / OKF 体检)报问题**不该**让整轮判失败。

    它们报的是**内容发现**(有页待补、有条目违规),不是基础设施故障。
    把它们算进失败,cron 会因为"知识库里有几页没写完"天天报警 —— 那样的告警
    很快就没人看了,真故障也跟着被淹没。这条区分是刻意的。
    """
    v, path = _repo(tmp_path, accounting_ok=False)
    r = _run(v, path, tmp_path)
    assert r.returncode == 0, \
        "记账类步骤报问题不该让整轮失败:" + (r.stdout + r.stderr)[-700:]
