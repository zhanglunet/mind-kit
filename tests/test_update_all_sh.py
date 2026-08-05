"""update-all.sh 的行为测试(本机全量更新编排)。
契约:
- `--dry-run` 打印有序计划(日报→编译→订阅→门户→文档站),退出 0,不执行任何步骤。
- 计划里对缺工具的步骤标「缺 <tool>,将跳过」,对就绪的标「<tool> 就绪」。
- `--pull` 会把"拉取最新代码"列为第 0 步;不带则提示可加。
- 未知参数 → 用法 + 非零退出;`bash -n` 语法干净。
纯 .sh 用 subprocess 测(见 tests/README.md)。
"""
import sys
import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SH = REPO / "scripts" / "update-all.sh"


def _run(*args, env=None):
    return subprocess.run(["bash", str(SH), *args], cwd=str(REPO),
                          capture_output=True, text=True, env=env)


def _py_dir():
    import shutil
    return str(Path(shutil.which(sys.executable)).parent)


def test_syntax_ok():
    assert subprocess.run(["bash", "-n", str(SH)]).returncode == 0


def test_dry_run_lists_steps_in_order():
    r = _run("--dry-run")
    assert r.returncode == 0, r.stderr
    out = r.stdout
    order = ["日报", "编译", "订阅台账", "门户入口", "文档站"]
    idx = [out.find(x) for x in order]
    assert all(i >= 0 for i in idx), f"计划应含全部步骤:{out}"
    assert idx == sorted(idx), f"步骤顺序不对:{out}"


def test_dry_run_does_not_execute(tmp_path):
    """dry-run 不得产生副作用。

    原来断言 `not (REPO/browse/.update-all.log).exists()` —— 但那个文件**不是**
    update-all.sh 写的(写它的是 brain-server.py 与飞书机器人),而且 browse/ 在
    .gitignore 里、一旦生成就永久留着。于是这条断言测的是"这台机器有没有点过门户的
    全量更新按钮",在 VM 和笔记本上永久红,在开发容器里永久绿。改成前后对比。
    """
    r = _run("--dry-run")
    assert r.returncode == 0
    # 钉脚本**自己**的可观测行为,而不是别的进程留下的产物:
    # step() 打的 "▶ " 前缀只在真跑时出现,dry-run 在打完计划就 exit 0。
    assert "▶" not in r.stdout, f"dry-run 不该执行任何步骤:{r.stdout[-400:]}"


def test_dry_run_marks_missing_tools(tmp_path):
    # PATH 指向空目录(dry-run 只用 shell 内建,无需外部二进制)、HOME 无 go/bin、
    # brew 前缀指到不存在目录(脚本默认把 /opt/homebrew/bin 补进 PATH,会泄露本机
    # 已装的 pandoc)→ sage-wiki / pandoc 都解析不到。
    # 注意两者措辞不同(2026-07-28 起):**核心**工具缺失会判失败、要在计划里就说清,
    # 可选工具才是"将跳过"。
    import shutil
    onlybash = tmp_path / "onlybash"
    onlybash.mkdir()
    (onlybash / "bash").symlink_to(shutil.which("bash"))   # 只放 bash,sage-wiki/pandoc 解析不到
    env = {**os.environ, "PATH": str(onlybash), "HOME": str(tmp_path),
           "UPDATE_ALL_BREW_BIN": str(tmp_path / "no-brew")}
    r = _run("--dry-run", env=env)
    assert r.returncode == 0, r.stderr
    assert "缺核心工具 sage-wiki" in r.stdout, r.stdout      # 核心:会判失败
    assert "缺 pandoc,将跳过" in r.stdout, r.stdout          # 可选:静默跳过没问题


def test_dry_run_marks_present_tools(tmp_path):
    # 造 sage-wiki / pandoc 桩放进 PATH → 两步都标"就绪"
    bind = tmp_path / "bin"
    bind.mkdir()
    for name in ("sage-wiki", "pandoc"):
        s = bind / name
        s.write_text("#!/bin/sh\nexit 0\n")
        s.chmod(0o755)
    env = {**os.environ, "PATH": f"{bind}:{_py_dir()}:/usr/bin:/bin", "HOME": str(tmp_path)}
    r = _run("--dry-run", env=env)
    assert r.returncode == 0, r.stderr
    assert "sage-wiki 就绪" in r.stdout and "pandoc 就绪" in r.stdout, r.stdout


def test_pull_flag_adds_step_zero():
    r = _run("--pull", "--dry-run")
    assert r.returncode == 0
    assert "git pull" in r.stdout and "拉取" in r.stdout


def test_no_pull_hints_optional():
    r = _run("--dry-run")
    assert "--pull" in r.stdout


def test_unknown_arg_usage_nonzero():
    r = _run("--bogus")
    assert r.returncode != 0
    assert "用法" in (r.stdout + r.stderr)


def test_daily_launchagent_plist_valid():
    # 每日自启的 LaunchAgent:XML/plist 合法、Label 正确、确实调 update-all.sh、每日定时
    import plistlib
    plist = REPO / "scripts" / "com.mind.update-all.plist"
    d = plistlib.loads(plist.read_bytes())
    assert d["Label"] == "com.mind.update-all"
    assert "StartCalendarInterval" in d, "须是定时(每日)而非 KeepAlive"
    assert any("update-all.sh" in a for a in d["ProgramArguments"]), "须调用 update-all.sh"


# ═══ 真机审查暴露:锁与静默成功 ═══════════════════════════════

def _synthetic_vault(tmp_path):
    """把 update-all.sh 与解析库拷进一个空壳仓。

    **绝不能对真实仓库跑不带 --dry-run 的 update-all.sh**:一旦锁没拿到
    (macOS 没有 flock(1),脚本原先直接降级为"无保护继续跑"),它会真的把
    日报 → compile.sh(含 vault 提交)→ 门户 → 文档站对着用户的知识库跑一遍,
    还会被 timeout 从中途掐断。空壳仓里这些步骤只会各自失败,伤不到任何东西。
    """
    import shutil
    v = tmp_path / "mind"
    (v / "scripts").mkdir(parents=True)
    for f in ("update-all.sh", "_pyresolve.sh"):
        shutil.copy(REPO / "scripts" / f, v / "scripts" / f)
    return v


def _run_real(vault, env_extra=None, timeout=90):
    env = {**os.environ, "HOME": str(vault.parent),          # 别让 ~/go/bin/sage-wiki 混进来
           "UPDATE_ALL_BREW_BIN": str(vault.parent / "nobrew"),
           **(env_extra or {})}
    return subprocess.run(["bash", str(vault / "scripts" / "update-all.sh")],
                          cwd=str(vault), capture_output=True, text=True,
                          timeout=timeout, env=env)


def test_takes_the_cross_process_lock(tmp_path):
    """update-all.sh **自己**必须取锁。

    2026-07-28 审查发现:锁只加在 brain-server 与飞书机器人两条路上,而 cron 跑的
    是本脚本 —— 门户按钮点一下、cron 同时到点,两轮编译照样并发。锁形同虚设。
    """
    import fcntl
    import shutil
    if shutil.which("flock") is None:
        pytest.skip("本条验的是 flock(1) 路径;无 flock 时走 mkdir 兜底,另有测试")
    vault = _synthetic_vault(tmp_path)
    fd = os.open(vault / ".update-all.lock", os.O_CREAT | os.O_RDWR)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        r = _run_real(vault)
        assert "已有一轮" in r.stdout or "在跑" in r.stdout, \
            "锁被占时要说清为什么没跑:" + r.stdout[-300:]
        # exit 0 而非非零:用户手点一次编译,不该让 cron 每天发一封失败邮件
        assert r.returncode == 0, f"锁冲突是正常情况,应退 0,实际 {r.returncode}"
    finally:
        os.close(fd)


def test_lock_works_without_flock_binary(tmp_path):
    """没有 flock(1) 也必须有跨进程互斥 —— macOS 上就没有这个二进制。

    原来是 `if command -v flock; …; else echo "⚠ 无 flock,跳过互斥保护"; fi`,
    **else 分支之后直接往下跑真实步骤**。也就是说用户笔记本(门户按钮 + 飞书机器人 +
    每日定时三条路都在用)上,这把锁从来就不存在。我先前还说过"本机有锁,跨机器才没有"
    —— 那句话错了两次:先是本脚本压根没取锁,修完之后 macOS 上仍然没有。
    """
    import shutil
    vault = _synthetic_vault(tmp_path)
    farm = tmp_path / "noflock"
    farm.mkdir()
    for d in os.environ.get("PATH", "").split(os.pathsep):
        if not d or not os.path.isdir(d):
            continue
        try:
            entries = list(os.scandir(d))
        except OSError:
            continue                      # 没权限读的目录直接跳过(非 root 跑测试很常见)
        for e in entries:
            if e.name != "flock" and not os.path.lexists(farm / e.name):
                os.symlink(e.path, farm / e.name)
    assert shutil.which("flock", path=str(farm)) is None

    # 造一把「持有者还活着」的锁:用本进程 PID(必然存在)
    lockdir = vault / ".update-all.lock.d"
    lockdir.mkdir()
    (lockdir / "pid").write_text(str(os.getpid()), encoding="utf-8")

    r = _run_real(vault, {"PATH": str(farm)})
    assert "已有一轮" in r.stdout or "在跑" in r.stdout, \
        "无 flock 时也必须挡住重入,而不是无保护继续跑:" + (r.stdout + r.stderr)[-400:]
    assert r.returncode == 0, f"锁冲突应退 0,实际 {r.returncode}"


def test_stale_lock_is_cleared_not_a_deadlock(tmp_path):
    """持有者已经死了的陈旧锁必须被清掉,否则机器崩过一次就永久卡住。"""
    import shutil
    vault = _synthetic_vault(tmp_path)
    farm = tmp_path / "noflock2"
    farm.mkdir()
    for d in os.environ.get("PATH", "").split(os.pathsep):
        if not d or not os.path.isdir(d):
            continue
        try:
            entries = list(os.scandir(d))
        except OSError:
            continue
        for e in entries:
            if e.name != "flock" and not os.path.lexists(farm / e.name):
                os.symlink(e.path, farm / e.name)

    lockdir = vault / ".update-all.lock.d"
    lockdir.mkdir()
    (lockdir / "pid").write_text("999999", encoding="utf-8")   # 几乎不可能存在的 PID

    r = _run_real(vault, {"PATH": str(farm)})
    assert "陈旧" in r.stdout or "stale" in r.stdout.lower(), \
        "陈旧锁应被识别并清理,且说出来:" + (r.stdout + r.stderr)[-400:]
    assert "已有一轮" not in r.stdout, "陈旧锁不该被当成有人在跑"


def test_missing_core_tool_really_exits_nonzero(tmp_path):
    """缺核心工具时**真跑**必须非零退出 —— 不能只验计划文本。

    原来这条 docstring 写的是「缺 sage-wiki 时不许退 0」,但它跑的是 --dry-run,
    而 dry-run 无条件 exit 0;断言也只查计划里的措辞。也就是说"cron 天天报绿、
    Wiki 悄悄停摆"这个真正要防的场景,从来没被验证过 —— 契约写在注释里,
    检查落在别处。这条补上真跑路径(在空壳仓里,伤不到真实知识库)。
    """
    vault = _synthetic_vault(tmp_path)
    r = _run_real(vault, {"PATH": "/usr/bin:/bin"})
    assert "缺核心工具 sage-wiki" in r.stdout, \
        "核心工具缺失要点名:" + (r.stdout + r.stderr)[-500:]
    assert r.returncode != 0, "核心工具缺失必须判失败,否则 cron 永远报绿"


def test_missing_core_tool_is_flagged_in_the_plan(tmp_path):
    """计划里就要标明缺的是**核心**工具(会判失败),而不是"将跳过"。

    真跑的非零退出由上一条钉死;这条只管 dry-run 的措辞。

    断言必须钉在**核心工具专属的措辞**上:只看退出码会假绿——PATH 掐太狠时
    是别的步骤失败导致的非零,测出来的不是这条契约(第一版就这么翻的车)。
    """
    r = subprocess.run(["bash", str(SH), "--dry-run"], cwd=str(REPO),
                       capture_output=True, text=True, timeout=60,
                       env={**os.environ, "HOME": str(tmp_path),
                            "PATH": "/usr/bin:/bin",
                            "UPDATE_ALL_BREW_BIN": str(tmp_path / "nobrew")})
    assert "缺核心工具" in r.stdout or "核心·必需" in r.stdout, \
        "计划里就该标明核心工具缺失会导致失败而非静默跳过:" + r.stdout[-400:]


def test_runtime_lock_file_not_tracked():
    """运行期锁文件不得入库。

    2026-07-28:`.update-all.lock` 被跑测试时创建、然后随手 `git add -A` 带进了仓库
    —— 克隆下来就带着一个别人机器上的 0 字节锁,毫无意义还容易让人以为是配置。
    """
    # check=True:git 失败时 stdout 为空,`assert not bad` 会恒真 —— 空转的门禁比没有更坏
    r = subprocess.run(["git", "-C", str(REPO), "ls-files"],
                       capture_output=True, text=True, check=True)
    tracked = r.stdout.split("\n")
    assert len(tracked) > 10, "入库清单异常地少,门禁可能在空转"
    bad = [f for f in tracked if f.endswith(".lock")]
    assert not bad, "这些运行期锁文件被跟踪了,应 gitignore:" + ", ".join(bad)


# ═══ 内容库同步:编译前拉、编译后推 ═══════════════════════════

def test_plan_includes_vault_pull_before_compile_and_push_after():
    """计划里必须有「拉内容库」(在编译**之前**)与「推内容库」(在编译**之后**)。

    2026-07-29 真机:VM 的 mind-vault 落后远端 10 个提交,于是它一直在旧基线上编译,
    产物必然和远端对不上;编译完又不推,提交只堆在本地。cron 一开就是每天重演。
    部署文档 §7 提过要在 cron 前置一条 pull —— 但那是写在文档里的软规范,
    按本仓原则(「Prompt 不是检查器」)必须做进脚本本身。
    """
    out = _run("--dry-run").stdout
    i_pull = out.find("拉取内容库")
    i_comp = out.find("编译")
    i_push = out.find("推送内容库")
    assert i_pull >= 0, f"计划缺「拉取内容库」:{out}"
    assert i_push >= 0, f"计划缺「推送内容库」:{out}"
    assert i_pull < i_comp, "拉内容库必须在编译之前(否则编的是旧基线)"
    assert i_push > i_comp, "推内容库必须在编译之后(否则推的是上一轮的产物)"


def test_vault_pull_failure_is_not_silent(tmp_path):
    """内容库拉取失败必须计入失败,不能继续编译还报绿。

    拉不动通常意味着"本地有未推的提交"或"网络/权限出问题"——
    这两种情况下继续编译只会让两端分叉得更远。
    """
    vault = _synthetic_vault(tmp_path)
    # 合成仓里没有内容库、也没有 remote:拉取必然失败
    r = _run_real(vault, {"PATH": "/usr/bin:/bin"})
    both = r.stdout + r.stderr
    assert "内容库" in both, "要说清是内容库同步这一步出的问题:" + both[-500:]
    assert r.returncode != 0, "内容库拉取失败还退 0 = 又一次假绿"


# ---------- 机器级开关:VM 不该每天重建文档站 ----------
#
# 2026-08-04 实测:VM 的 cron 每天跑 build-site.sh 重新生成 site/*.html,
# 而两台机器的 pandoc 版本不同 → 渲染出的 HTML 有差异 → 代码仓天天是脏的
# → `git pull` 每次都被「Your local changes would be overwritten」拦下。
# 那批 HTML 在 VM 上**没有任何消费者**(aip.cab 由 Cloudflare 从 GitHub main
# 部署,不走 VM)。所以给它一个机器级开关,VM 上关掉。
#
# 关键约束:**跳过的理由必须说真话**。沿用既有的「缺工具就跳过」通道会打印
# 「未装 pandoc」——那是假的,会把人引去装一个已经装了的东西。


def test_site_step_skipped_when_switch_off():
    """MIND_BUILD_SITE=0 → 文档站不出现在计划里(或明确标为将跳过)。"""
    env = {**os.environ, "MIND_BUILD_SITE": "0"}
    r = _run("--dry-run", env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    line = [l for l in r.stdout.splitlines() if "[文档站]" in l]
    assert line, "计划里应仍列出文档站这一步(只是标明将跳过):" + r.stdout[-400:]
    assert "跳过" in line[0], "关掉开关后该标明将跳过:" + line[0]


def test_site_skip_reason_tells_the_truth_not_missing_pandoc():
    """关掉开关时的理由必须是「开关关了」,**不能**说成「未装 pandoc」。

    说假理由比不说更糟:它会把人支去装一个已经装好的东西,
    而真正的原因(这台机器不负责生成文档站)一直没人知道。
    """
    env = {**os.environ, "MIND_BUILD_SITE": "0"}
    r = _run("--dry-run", env=env)
    line = [l for l in r.stdout.splitlines() if "[文档站]" in l][0]
    assert "MIND_BUILD_SITE" in line or "关闭" in line, \
        "跳过理由要指明是开关关的:" + line
    assert "未装 pandoc" not in line and "缺 pandoc" not in line, \
        "pandoc 明明装着,不许报成缺 pandoc:" + line


def test_site_step_on_by_default():
    """不设开关时行为不变 —— 笔记本照旧生成文档站。"""
    env = {k: v for k, v in os.environ.items() if k != "MIND_BUILD_SITE"}
    r = _run("--dry-run", env=env)
    line = [l for l in r.stdout.splitlines() if "[文档站]" in l][0]
    assert "MIND_BUILD_SITE" not in line, "默认不该提开关:" + line


def test_switch_off_counts_as_skip_not_failure(tmp_path):
    """关掉开关是**跳过**,不是失败 —— 否则 cron 天天发失败邮件。"""
    vault = _synthetic_vault(tmp_path)
    r = _run_real(vault, env_extra={"MIND_BUILD_SITE": "0"})
    out = r.stdout + r.stderr
    assert "[文档站]" in out
    seg = out[out.index("[文档站]"):][:200]
    assert "跳过" in seg, "关掉开关应记为跳过:" + seg
    assert "未装 pandoc" not in seg, "不许谎报缺 pandoc:" + seg


# ---------- 隐私兜底网的运行时检查 ----------
#
# 2026-08-04 真机事故:VM 上的 .gitignore 被**整个覆盖**,129 行只剩一行 `.sage/`
# (幸存的正是 sage-wiki 自己的缓存目录,像是它用最小模板覆盖而非追加)。
# 被抹掉的包括密钥形状(.env / *.key / secrets.*)、raw/private 冷存层,
# 以及全部个人内容软链 —— CLAUDE.md 那条「那些路径在 .gitignore 里,`git add`
# 会静默什么都不干」的兜底,当场失效。
#
# 仓库侧已有门禁(tests/test_no_personal_identifiers.py),但它只护得住**仓库里的
# 版本**,护不住**运行中的机器**被第三方工具改写。所以每日编排开跑前先问 git 一句:
# 那几个路径现在还被忽略吗?不问,就要等到某次 `git add -A` 之后才知道。

SHIELD_MARKER = "隐私兜底网"   # 这条检查自己的招牌:别的步骤失败不会打出这四个字


def _dual_repo_vault(tmp_path, gitignore):
    """合成一个**双库布局**的仓:个人目录是指向相邻内容库的软链。

    必须是软链而非真目录 —— 检查只管软链(单库模式下 `_wiki/` 等是真目录、本来
    就该入库,那种仓一条都不该查)。拿真目录搭的合成仓根本触发不了这条检查,
    测出来的就是别的东西了。
    """
    v = _synthetic_vault(tmp_path)
    data = tmp_path / "mind-vault"
    (v / "reports").mkdir(exist_ok=True)
    for rel in ("_wiki", "material", "raw", "writing",
                "reports/daily", "reports/weekly", "reports/lint"):
        (data / rel).mkdir(parents=True, exist_ok=True)
        (v / rel).symlink_to(data / rel)
    (v / ".gitignore").write_text(gitignore, encoding="utf-8")
    subprocess.run(["git", "-C", str(v), "init", "-q"], check=True)
    return v


def test_refuses_to_run_when_gitignore_stops_shielding_personal_dirs(tmp_path):
    """个人目录不再被 git 忽略时,必须**开跑前就停住并明说**,而不是照常跑完报绿。

    问的是 `git check-ignore`,不是读 .gitignore 文本:规则写成什么样不重要,
    **git 此刻到底忽不忽略**才是事实(还顺带覆盖 .git/info/exclude 与全局 excludes)。
    """
    v = _dual_repo_vault(tmp_path, ".sage/\n")          # 复刻真机被覆盖后的样子
    r = _run_real(v)
    out = r.stdout + r.stderr
    assert SHIELD_MARKER in out, "兜底网破了必须明说:" + out[-700:]
    assert "▶" not in out, "要在**开跑前**停住,不许先跑一半再说:" + out[-700:]
    assert r.returncode != 0, "兜底网破了还退 0 = 又一次「失败伪装成成功」"


def test_shield_failure_says_how_to_fix_it(tmp_path):
    """光报警没用:得说清怎么修、以及怎样显式绕过。

    否则现场只有一句"出错了",人只会去脚本里把这段删掉 —— 那比没有检查更糟。
    """
    v = _dual_repo_vault(tmp_path, ".sage/\n")
    r = _run_real(v)
    out = r.stdout + r.stderr
    assert ".gitignore" in out, "要点名是哪个文件出的事:" + out[-500:]
    assert "MIND_SKIP_SHIELD_CHECK" in out, \
        "要给出具名的绕过方式,否则人会直接改脚本:" + out[-500:]


def test_intact_gitignore_does_not_trip_the_check(tmp_path):
    """兜底网完好时不许误报 —— 否则这条检查很快会被人加 `|| true` 绕过。

    用的就是本仓真实的 .gitignore:这条检查跟仓库里那份约定是**同一个事实**,
    拿删减版来测等于给自己放水。
    """
    v = _dual_repo_vault(tmp_path, (REPO / ".gitignore").read_text(encoding="utf-8"))
    r = _run_real(v)
    out = r.stdout + r.stderr
    assert SHIELD_MARKER not in out, "兜底网完好时不该报警:" + out[-600:]
    assert "▶" in out, "检查通过就该照常往下跑:" + out[-600:]


def test_shield_check_is_silent_outside_a_git_repo(tmp_path):
    """不在 git 工作树里(临时副本、解压出来的一份)就无从问起 —— 静默放行。

    这里**不能**把"问不到"当成"破了":那会让所有合成环境与非 git 副本永久红,
    检查很快就被整段注释掉。
    """
    v = _synthetic_vault(tmp_path)
    r = _run_real(v)
    assert SHIELD_MARKER not in (r.stdout + r.stderr)


def test_shield_check_has_a_named_escape_hatch(tmp_path):
    """留一个**具名**开关:绕过必须是显式动作(写得出变量名),而不是默默失效。"""
    v = _dual_repo_vault(tmp_path, ".sage/\n")
    r = _run_real(v, {"MIND_SKIP_SHIELD_CHECK": "1"})
    out = r.stdout + r.stderr
    assert SHIELD_MARKER not in out, "显式绕过后不该再拦:" + out[-400:]
    assert "▶" in out, "绕过后要照常往下跑:" + out[-400:]
