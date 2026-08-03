"""解释器卫生:别假设 `python3` 就是对的那个 Python。

2026-07-28 真机(阿里云 Anolis)暴露:系统 `python3` 是 **3.6.8**(EOL),
而依赖装在 `.venv`(3.11)里。于是——

- 测试用 `subprocess.run(["python3", ...])` 起子进程 → 子进程是 3.6 →
  `from __future__ import annotations` SyntaxError、`date.fromisoformat` 不存在、
  `subprocess.run(capture_output=)` TypeError…… 43 个测试红,**全是同一个根因**。
- shell 脚本里的 `python3 scripts/xxx.py` 同理:cron 一跑就全线失败。
- pre-push 钩子找不到 pytest → **静默跳过** → 推送前的测试门禁等于没有。

契约:凡起 Python 子进程,都必须用「跑得起本项目的那个解释器」。
"""
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def test_tests_never_hardcode_python3():
    """测试起子进程必须用 sys.executable —— 硬编码 python3 会跑到别的解释器上。

    只查**命令列表首位**(`["python3", ...]`)这种真正危险的形态:
    把 "python3" 当输出文本匹配、或当假二进制的文件名,都是正当用法,
    一刀切会逼人给正确代码加豁免(门禁太钝比没有门禁更烦)。
    """
    danger = re.compile(r'\[\s*["\']python3["\']')
    bad = []
    for f in sorted((REPO / "tests").glob("*.py")):
        if f.name == Path(__file__).name:
            continue
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if danger.search(line) and "noqa" not in line:
                bad.append(f"{f.name}:{i}: {line.strip()[:70]}")
    assert not bad, ("这些测试用硬编码 python3 起子进程(真机上可能是 EOL 的 3.6),"
                     "改用 sys.executable:\n  " + "\n  ".join(bad))


def test_shell_scripts_resolve_python():
    """所有会起 Python 的 shell 脚本都必须解析解释器,不能裸调 python3。

    第一版只查了 3 个核心脚本,漏了 **vault.sh** —— 那是提交漏斗,
    写集校验在真机上直接崩(capture_output 是 3.7+)。门禁漏一个就等于没有。

    例外:vm-precheck.sh / vm-setup.sh 的职责**就是**挑 python,提到 python3 是正当的。
    """
    EXEMPT = {"vm-precheck.sh", "vm-setup.sh", "_pyresolve.sh"}
    bad = []
    targets = [p for p in (REPO / "scripts").glob("*.sh") if p.name not in EXEMPT]
    targets.append(REPO / ".githooks" / "pre-push")
    for p in targets:
        if not p.exists():
            continue
        src = p.read_text(encoding="utf-8")
        uses_py = any(l.strip().startswith("python3 ") or " python3 " in l
                      for l in src.splitlines() if not l.strip().startswith("#"))
        if not uses_py:
            continue
        if "_pyresolve.sh" not in src:
            bad.append(f"{p.name}: 用 python3 但没接解释器解析")
    assert not bad, "\n  ".join([""] + bad)


def test_missing_pyresolve_is_fatal_not_empty_interpreter(tmp_path):
    """`_pyresolve.sh` 缺失时必须**立刻硬失败**,不能带着空 MIND_PY 往下跑。

    这几个 cron 脚本都是 `set -uo pipefail`(无 -e)+ 每步 `|| echo "⚠ …"`:
    source 失败 → mind_python 未定义 → MIND_PY 为空 → 每步变成 `"" scripts/x.py`
    → 步步 command not found、步步被 `||` 吞掉、**整脚本仍退 0**。
    cron 日志一片"完成",实际一件事没做。
    """
    import shutil
    import pytest
    # 这批脚本是私有仓专属(publish/DELETE.txt),公开版树里没有 → 无可测对象就跳过。
    names = [n for n in ("kd-weekly-sync.sh", "feishu-weekly-news.sh",
                         "feishu-daily-docs.sh", "feishu-token-keepalive.sh")
             if (REPO / "scripts" / n).exists()]
    if not names:
        pytest.skip("这批 cron 脚本是私有仓专属,公开版无此文件")
    fake = tmp_path / "mind"
    (fake / "scripts").mkdir(parents=True)
    for name in names:
        shutil.copy(REPO / "scripts" / name, fake / "scripts" / name)
    # 故意不拷 _pyresolve.sh
    for name in names:
        r = subprocess.run(["bash", str(fake / "scripts" / name)], cwd=str(fake),
                           capture_output=True, text=True, timeout=60,
                           env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path)})
        assert r.returncode != 0, f"{name}:缺解释器解析库还退 0 = 假绿"
        assert "解释器" in (r.stdout + r.stderr), \
            f"{name}:要说清楚是解释器解析没了,别让人对着一串 command not found 猜"


def test_pyresolve_prefers_venv(tmp_path):
    """解析顺序:.venv/bin/python > MIND_PYTHON > python3。"""
    lib = REPO / "scripts" / "_pyresolve.sh"
    assert lib.exists(), "缺 scripts/_pyresolve.sh"
    venv_py = tmp_path / ".venv" / "bin" / "python"
    venv_py.parent.mkdir(parents=True)
    venv_py.write_text("#!/bin/sh\necho venv\n", encoding="utf-8")
    venv_py.chmod(0o755)
    r = subprocess.run(["bash", "-c",
                        f'. "{lib}"; mind_python "{tmp_path}"'],
                       capture_output=True, text=True, timeout=20)
    assert r.stdout.strip() == str(venv_py), f"应优先 venv:{r.stdout}{r.stderr}"


def test_pyresolve_falls_back_to_env_then_python3(tmp_path):
    """没有 .venv 时:MIND_PYTHON > python3。

    PATH 用**受控的假 bin 目录**,不用真实的 /usr/bin —— 后者会把断言变成
    "本机的 python3 恰好是几"：在开发容器里 python3 是 3.11(够新,退回 python3),
    在部署 VM 上是 3.6(不够新,于是去挑 python3.11)。同一份代码,两个结果。
    """
    import shutil
    lib = REPO / "scripts" / "_pyresolve.sh"
    bind = tmp_path / "bin"
    _fake_bin(bind, "python3", "#!/bin/sh\nexit 0\n")     # 版本探测通过 = 够新
    fake = _fake_bin(tmp_path, "mypy3", "#!/bin/sh\necho env\n")
    BASH = shutil.which("bash")

    r = subprocess.run([BASH, "-c", f'. "{lib}"; mind_python "{tmp_path}"'],
                       capture_output=True, text=True, timeout=20,
                       env={"PATH": str(bind), "MIND_PYTHON": str(fake)})
    assert r.stdout.strip() == str(fake), f"其次用 MIND_PYTHON:{r.stdout}{r.stderr}"

    r2 = subprocess.run([BASH, "-c", f'. "{lib}"; mind_python "{tmp_path}"'],
                        capture_output=True, text=True, timeout=20,
                        env={"PATH": str(bind)})
    assert r2.stdout.strip() == "python3", f"python3 够新就用它:{r2.stdout}{r2.stderr}"


def _fake_bin(d: Path, name: str, body: str) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text(body, encoding="utf-8")
    p.chmod(0o755)
    return p


def test_pyresolve_skips_too_old_python3_for_a_versioned_one(tmp_path):
    """裸 `python3` 太老时,要去找 `python3.11` 这样的版本化名字,而不是硬用它。

    真机就是这个形状:`dnf install python3.11` 之后 /usr/bin/python3.11 有了,
    但 `python3` 仍指向 3.6。没建 .venv 之前(新克隆、或 vm-setup.sh 跑到一半),
    所有脚本都会撞上 3.6 —— 报出来的是 `capture_output` TypeError 之类的鬼话,
    没人能从那句话猜到"你的 python3 太老了"。
    """
    import shutil
    lib = REPO / "scripts" / "_pyresolve.sh"
    bind = tmp_path / "bin"
    _fake_bin(bind, "python3", "#!/bin/sh\nexit 1\n")          # 版本探测不过 = 太老
    _fake_bin(bind, "python3.11", f'#!/bin/sh\nexec "{sys.executable}" "$@"\n')
    # PATH 只放这两个:否则会扫到本机真实的 python3.12/3.13(那是**正确**行为——
    # 挑最新的可用版本——但会让断言变成"本机装了哪些版本"这种环境依赖)
    r = subprocess.run([shutil.which("bash"), "-c", f'. "{lib}"; mind_python "{tmp_path}"'],
                       capture_output=True, text=True, timeout=30,
                       env={"PATH": str(bind)})
    assert r.stdout.strip() == "python3.11", \
        f"应改用版本化的 python3.11,实际:{r.stdout.strip()!r}{r.stderr}"


def test_pyresolve_warns_loudly_when_nothing_new_enough(tmp_path):
    """一个够新的都找不到时,要在 stderr 说人话,而不是让下游抛 TypeError。"""
    import shutil
    lib = REPO / "scripts" / "_pyresolve.sh"
    bind = tmp_path / "bin"
    _fake_bin(bind, "python3", "#!/bin/sh\nexit 1\n")
    # PATH 里只有那个太老的 python3(bash 用绝对路径起,免得连壳都找不到)
    r = subprocess.run([shutil.which("bash"), "-c", f'. "{lib}"; mind_python "{tmp_path}"'],
                       capture_output=True, text=True, timeout=30,
                       env={"PATH": str(bind)})
    assert "3.9" in r.stderr or "太老" in r.stderr, \
        f"没有够新的 Python 时必须明确告警,实际 stderr:{r.stderr!r}"
    assert r.stdout.strip() == "python3", "告警之后仍退回 python3(由调用方决定怎么办)"


def test_pre_push_hook_does_not_silently_skip_when_venv_exists():
    """钩子必须先找 venv 的 pytest —— 找不到就静默放行 = 推送门禁形同虚设。"""
    src = (REPO / ".githooks" / "pre-push").read_text(encoding="utf-8")
    assert "_pyresolve.sh" in src or ".venv" in src, \
        "pre-push 没有解析解释器,真机上会因系统 python3 无 pytest 而静默跳过"


def test_publish_refuses_push_without_pandoc():
    # publish-kit 是私有仓专属(公开版不向自己发布),公开版树里没有它 → 跳过。
    # 本文件其余几条(测试/脚本的解释器卫生)对公开版同样有效,故整体保留。
    """无 pandoc → site/ 用的是**私有版**旧产物,可能带出禁忌词。
    真机实测:恰好被禁忌词门禁拦住(命中了两条历史条目里的规则),
    但那是撞运气 —— 推送路径必须直接拒绝,不能靠碰巧。"""
    sh = REPO / "scripts" / "publish-kit.sh"
    if not sh.exists():
        import pytest
        pytest.skip("publish-kit.sh 是私有仓专属,公开版无此文件")
    src = sh.read_text(encoding="utf-8")
    i = src.index("无 pandoc")
    seg = src[max(0, i - 500):i + 500]
    assert "PUSH" in seg or "push" in seg, "无 pandoc 时要按是否推送区别对待"


# ═══ 门禁不许空转 ═══════════════════════════════════════════

def test_git_listing_in_tests_must_check_exit_code():
    """测试里读 `git ls-files` 的结果必须 check=True。

    2026-07-28 扫出:三道隐私门禁 + 一条锁文件门禁都写成
    `subprocess.run([... "ls-files" ...], capture_output=True).stdout`,
    没查退出码。git 一旦失败(最现实的是 cron 换用户跑导致 dubious ownership),
    stdout 为空 → 清单为空 → `assert not hits` **恒真**。
    报出来的绿不是"没查到问题",是"根本没查" —— 比没有门禁更坏,因为它让人放心。

    用 AST 判,不用正则:调用跨多行时正则会漏。
    """
    import ast
    bad = []
    for f in sorted((REPO / "tests").glob("*.py")):
        tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
            if name not in ("run", "check_output"):
                continue
            src = ast.dump(node)
            if "'ls-files'" not in src and '"ls-files"' not in src:
                continue
            ok = any(k.arg == "check" and getattr(k.value, "value", None) is True
                     for k in node.keywords)
            if not ok:
                bad.append(f"{f.name}:{node.lineno}")
    assert not bad, ("这些 git ls-files 调用没 check=True,失败时会静默返回空清单、"
                     "让门禁恒真:\n  " + "\n  ".join(bad))


def test_git_config_isolated_from_personal_machine(tmp_path):
    """全局 git 配置必须被隔离掉,否则个人机器上的设置会渗进合成仓。

    最现实的杀手是 `commit.gpgsign=true`:签名密钥换台机器就不在,
    合成仓的 `git commit` 直接失败,一批测试集体 ERROR —— 而在干净的容器/VM 上全绿。
    这里用一个"有毒"的 HOME 验证 conftest 的隔离真的压得住 ambient 配置。
    """
    import os
    poisoned = tmp_path / "home"
    poisoned.mkdir()
    (poisoned / ".gitconfig").write_text(
        "[commit]\n\tgpgsign = true\n[user]\n\tsigningkey = NOSUCHKEY\n", encoding="utf-8")

    repo = tmp_path / "r"
    repo.mkdir()
    env = {**os.environ, "HOME": str(poisoned)}
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True, env=env)
    (repo / "a.txt").write_text("x", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True, env=env)
    r = subprocess.run(["git", "-C", str(repo), "commit", "-qm", "t"],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 0, ("有毒的全局配置渗进来了(conftest 的隔离没生效):"
                               + r.stdout + r.stderr)


def test_precheck_tests_must_inject_machine_state():
    """断言「体检探测到了什么」的测试,必须自己把那些机器事实注入进去。

    这一类 bug 已经连续咬了四次,最后一次就发生在我为了修它而写的那条测试里:
    断言 `"进程中的 hermes 运行用户" not in stdout` —— 容器里没跑 Hermes 所以绿,
    VM 上真的跑着 Hermes,那句输出**是正确的**,于是红。
    我又一次把"本机恰好是什么状态"焊进了断言。

    规则:凡断言里出现下列**探测结论**措辞的,函数体内必须至少注入一个对应的钩子
    (MIND_HOME_ROOT / MIND_HERMES_USER_OVERRIDE / MIND_FAKE_HERMES_HOME / ps 垫片)。
    只断言段落标题(如 "Hermes" 三个字)不受此限 —— 那与机器状态无关。
    """
    import ast
    f = REPO / "tests" / "test_vm_scripts.py"
    if not f.exists():
        import pytest
        pytest.skip("test_vm_scripts.py 是私有仓专属")
    src = f.read_text(encoding="utf-8")
    tree = ast.parse(src, filename=str(f))
    VERDICTS = ("进程中的 hermes", "没检测到 Hermes", "发现 Hermes",
                "属主就是", "进不去", "路径对其他用户可达")
    HOOKS = ("MIND_HOME_ROOT", "MIND_HERMES_USER_OVERRIDE",
             "MIND_FAKE_HERMES_HOME", "_ps_shim_farm", "MIND_CHECK_PATH")
    bad = []
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or not node.name.startswith("test_"):
            continue
        body = ast.get_source_segment(src, node) or ""
        if "PRECHECK" not in body:
            continue
        # 只看**断言条件里**的字符串:注释和失败信息里出现这些措辞是正当的
        # (解释这个坑本身就要引用它们)。门禁太钝会逼人给正确代码加豁免。
        asserted = []
        for a in ast.walk(node):
            if isinstance(a, ast.Assert):
                asserted += [c.value for c in ast.walk(a.test)
                             if isinstance(c, ast.Constant) and isinstance(c.value, str)]
        blob = "\n".join(asserted)
        if any(v in blob for v in VERDICTS) and not any(h in body for h in HOOKS):
            bad.append(f"{node.name}:{node.lineno}")
    assert not bad, ("这些测试断言了体检的探测结论,却没注入机器状态 —— "
                     "结果取决于跑测机器跑没跑 Hermes / 路径属主是谁:\n  "
                     + "\n  ".join(bad))


def test_pipeline_never_swallows_vault_commit_failure():
    """调 `vault.sh commit` 的地方不许用 `|| true` / `|| echo` 把失败吞掉。

    2026-07-29 真机:vault.sh 自己内部把 commit 失败吞成「无改动可提交」,
    compile.sh 明明检查了退出码也没用 —— 上游报「成功 5 · 失败 0」,
    而编译产物全堆在暂存区没进库。修好 vault.sh 之后,得防着同样的吞法
    在调用侧重新长出来。
    """
    import re
    bad = []
    for name in ("compile.sh", "update-all.sh", "vault.sh"):
        p = REPO / "scripts" / name
        if not p.exists():
            continue
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            s = line.strip()
            if s.startswith("#") or "commit" not in s:
                continue
            if re.search(r"commit[^|]*\|\|\s*(true|echo|:)", s):
                bad.append(f"{name}:{i}: {s[:80]}")
    assert not bad, ("这些地方把提交失败吞掉了(失败会伪装成成功):\n  " + "\n  ".join(bad))
