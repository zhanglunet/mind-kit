"""共享门禁:代码库不得硬编码个人标识(可执行检查,非文字规范)。

CLAUDE.md 原则「Prompt 不是检查器」——想让"代码库不含个人内容"这条规范
必须被遵守,就得给它写可执行检查。本测试即该检查。

**设计要点:断言用「形状」而非「字面值」**——把真实 open_id / 真人昵称 /
私人群名写进测试文件,等于泄露仍在库里。所以:
- 身份 ID / 备份文件名用正则匹配其**形态**(ou_ + 32 位 hex、__ + 8 位 hex.jsonl);
- 姓名/群名这类无形态可匹配的,改为**正向断言**:相应脚本必须从环境变量读取,
  存在 env 变量名即意味着字面值已被移除。
"""
import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def _tracked(*globs, repo: Path = REPO):
    """已跟踪文件(只查入库的;工作区临时文件不管)。

    **git 失败必须炸,不能返回空列表**:下面三道隐私门禁都是 `assert not hits`,
    清单为空时它们**恒真**。真实触发场景——cron 以另一个用户身份跑,git 报
    dubious ownership 而非零退出——会让"代码库不含个人标识"这条门禁悄悄空转,
    报的绿不是"没查到问题",是"根本没查"。

    **另一个致命细节:`-z` + `core.quotepath=false`。** git 默认把非 ASCII 路径
    C 转义成 `"docs/guide/\\351\\243\\236..."`,`repo / p` 于是指向一个不存在的文件,
    `_read()` 把 OSError 吞成空串 —— 本仓 14 个中文名入库文件(含飞书数字分身.md、
    飞书群聊抽取.md 这些**最可能含 open_id / 群名**的)因此从未被扫描过。
    """
    r = subprocess.run(["git", "-C", str(repo), "-c", "core.quotepath=false",
                        "ls-files", "-z", *globs],
                       capture_output=True, text=True, check=True)
    return [repo / p for p in r.stdout.split("\0") if p.strip()]


def _read(p: Path) -> str:
    """读不出来就**抛**,不要返回空串。

    返回 "" 等于把这个文件从扫描面里悄悄移走 —— 正是 quotepath 转义那个 bug
    的第二级放大器:路径拼错 → 文件不存在 → OSError → 空串 → 门禁在这个文件上恒真。
    编码问题用 errors="replace" 兜(那是内容问题,文件确实读到了);
    文件读不到是**基础设施坏了**,必须炸出来。
    """
    return p.read_text(encoding="utf-8", errors="replace")


# ---------- 元门禁:门禁本身不许空转 ----------

def test_tracked_listing_fails_loudly_instead_of_returning_empty(tmp_path):
    """git 拿不到文件清单时要抛异常,而不是给个空列表让下面三条恒真。"""
    with pytest.raises(subprocess.CalledProcessError):
        _tracked("*", repo=tmp_path)          # 不是 git 仓库


def test_tracked_listing_actually_finds_files():
    """正常情况下清单必须非空 —— 否则下面的 `assert not hits` 什么也没验证。"""
    got = _tracked("scripts/**", "*.md")
    assert len(got) > 10, f"入库文件清单异常地少({len(got)}),隐私门禁可能在空转"


def test_read_raises_instead_of_silently_returning_empty(tmp_path):
    """读不到的文件必须抛异常 —— 静默返回空串 = 把它移出扫描面。"""
    with pytest.raises(OSError):
        _read(tmp_path / "根本不存在.md")


def test_tracked_listing_covers_non_ascii_filenames():
    """中文名文件必须真的被读到。

    git 默认 core.quotepath=true 会把它们 C 转义,拼出的路径根本不存在,
    `_read()` 再把 OSError 吞成空串 —— 门禁于是在**最该查的那批文件**上恒真。
    这里连"文件存在且读得出内容"一起断言,光有路径不算数。
    """
    cjk = [p for p in _tracked("docs/**", "*.md") if not p.name.isascii()]
    assert cjk, "一个中文名入库文件都没找到,转义八成又回来了"
    unreadable = [str(p) for p in cjk if not p.exists() or not _read(p).strip()]
    assert not unreadable, "这些中文名文件读不到(路径被转义了?):\n  " + "\n  ".join(unreadable)


# ---------- 形状匹配:身份 ID / 私人备份文件名 ----------

def test_no_feishu_open_id_literals():
    """飞书 open_id(ou_ + 32 位 hex)是可直接喂 lark-cli 枚举会话的真实身份标识。"""
    pat = re.compile(r"\bou_[0-9a-f]{24,}")
    hits = []
    for p in _tracked("scripts/**", "docs/**", "*.md", "*.yaml", "site/**"):
        if p.name == Path(__file__).name:
            continue
        for i, line in enumerate(_read(p).splitlines(), 1):
            if pat.search(line):
                hits.append(f"{p.relative_to(REPO)}:{i}")
    assert not hits, ("硬编码飞书 open_id(真实身份标识),改从环境变量读:\n  "
                      + "\n  ".join(hits))


def test_no_private_chat_backup_filename_literals():
    """备份出的会话 jsonl 形如「<群名>__<8位hex>.jsonl」,文件名本身就带私人群名。"""
    pat = re.compile(r"__[0-9a-f]{8}\.jsonl")
    hits = []
    for p in _tracked("scripts/**", "docs/**", "*.md", "site/**"):
        if p.name == Path(__file__).name:
            continue
        for i, line in enumerate(_read(p).splitlines(), 1):
            if pat.search(line):
                hits.append(f"{p.relative_to(REPO)}:{i}")
    assert not hits, ("硬编码私人会话备份文件名(含群名),改为按 env 指定的群名解析:\n  "
                      + "\n  ".join(hits))


def test_no_feishu_doc_tokens_in_tracked_files():
    """飞书文档 token 就是文档 ID,无法像密钥那样轮换;不得入库。

    只匹配**字面值**(15+ 位字母数字):`feishu_token: {token}` 这类 f-string
    模板是生成 frontmatter 的代码、值是变量,不算泄露(首版正则误伤了 4 处)。
    """
    pat = re.compile(r"\b(?:feishu_token|feishu_url)\s*[:=]\s*['\"]?[A-Za-z0-9]{15,}")
    hits = []
    for p in _tracked("scripts/**", "docs/**", "*.md", "site/**", "evaluation/**"):
        if p.name == Path(__file__).name:
            continue
        for i, line in enumerate(_read(p).splitlines(), 1):
            if pat.search(line):
                hits.append(f"{p.relative_to(REPO)}:{i}")
    assert not hits, "入库文件含飞书文档 token:\n  " + "\n  ".join(hits)


# ---------- 正向断言:身份类配置必须走环境变量 ----------

def test_identity_comes_from_env_not_literals():
    """姓名/群名无形态可匹配,故断言相应脚本确实从 env 读取(字面值已移除)。

    2026-08-06(服务化 M1)扩入三个本地渲染脚本:真名默认参数、点评机器人
    名单、简报机器人名——它们此前都以字面值写在代码里,属于同一类
    「个人标识不入库」违例;值改为逗号分隔时也从同一个变量读。
    """
    expect = {
        "scripts/feishu-token-keepalive.sh": ["MIND_FEISHU_OU"],
        "scripts/build-kd-weekly.py": ["MIND_KD_GROUP", "MIND_KD_BOTS"],
        "scripts/kd-weekly-sync.sh": ["MIND_KD_GROUP"],
        "scripts/feishu-fetch-chat-docs.py": ["MIND_FEISHU_SELF"],
        "scripts/build-feishu-site.py": ["MIND_FEISHU_SELF"],
        "scripts/build-feishu-brief.py": ["MIND_FEISHU_BRIEF_BOTS"],
    }
    missing = [f"{f} 应从 {var} 读取" for f, envs in expect.items() for var in envs
               if (REPO / f).exists() and var not in _read(REPO / f)]
    assert not missing, "身份类配置须走环境变量:\n  " + "\n  ".join(missing)


def test_kd_weekly_fails_clearly_without_group(tmp_path):
    """未设 MIND_KD_GROUP 时必须明确报错退出并点名变量(FR-MOD-02 契约)。

    这条行为 2026-07-25 就写进了脚本(SystemExit + 可操作指引),但一直没有
    测试钉住——服务化 M1 起它是发行集 env 契约的样板,不能只靠源码注释活着。
    """
    import os
    import sys
    py = REPO / "scripts" / "build-kd-weekly.py"
    if not py.exists():
        return
    env = {k: v for k, v in os.environ.items() if k not in ("MIND_KD_GROUP",)}
    r = subprocess.run([sys.executable, str(py)], capture_output=True, text=True,
                       env=env, cwd=str(REPO), timeout=60)
    assert r.returncode != 0, "缺群名配置应非零退出"
    assert "MIND_KD_GROUP" in (r.stdout + r.stderr), \
        "报错须点名缺失的环境变量:" + (r.stdout + r.stderr)[:300]


def test_keepalive_fails_clearly_without_identity(tmp_path):
    """未设 MIND_FEISHU_OU 时必须明确报错退出,而不是拿空值去调 lark-cli。"""
    sh = REPO / "scripts" / "feishu-token-keepalive.sh"
    if not sh.exists():
        return
    import os
    env = {k: v for k, v in os.environ.items() if k != "MIND_FEISHU_OU"}
    env["PATH"] = "/usr/bin:/bin"      # 无 lark-cli,确保是身份检查先拦下
    r = subprocess.run(["bash", str(sh)], capture_output=True, text=True,
                       env=env, cwd=str(REPO), timeout=30)
    assert r.returncode != 0, "缺身份配置应非零退出"
    assert "MIND_FEISHU_OU" in (r.stdout + r.stderr), \
        "报错须点名缺失的环境变量,给出可操作指引:" + (r.stdout + r.stderr)[:300]


# ---------- 隐私兜底网本身要有门禁 ----------
#
# CLAUDE.md 的硬约束靠一句话成立:「那些路径在 mind/.gitignore 里,git add 会静默
# 什么都不干」。也就是说 **.gitignore 里那几行就是防止个人内容误入代码仓的最后一道网**。
# 而在 2026-08-04 之前,**没有任何测试盯着它们** —— 谁(或哪次合并冲突)把某行删了,
# 都不会有人发现,直到某天一次 git add -A 把整个知识库加进代码仓。

PERSONAL_PATHS = ["/raw", "/_wiki", "/material", "/writing",
                  "/reports/daily", "/reports/weekly", "/reports/lint", "/browse/"]


def test_gitignore_still_shields_personal_content():
    """`.gitignore` 必须挡住所有个人内容目录 —— 这是最后一道网,不许悄悄失效。"""
    lines = {l.strip() for l in (REPO / ".gitignore").read_text(encoding="utf-8").splitlines()}
    missing = [p for p in PERSONAL_PATHS if p not in lines and p.rstrip("/") not in lines]
    assert not missing, (
        "`.gitignore` 少了这些个人内容路径,代码仓失去兜底:\n  " + "\n  ".join(missing)
        + "\n(CLAUDE.md 的「git add 会静默什么都不干」正是靠它们成立)")


def test_no_personal_directory_is_actually_tracked():
    """行为层再兜一道:个人目录**一个文件都不许被 git 跟踪**。

    只查 .gitignore 文本还不够 —— 已经被跟踪的文件,加进 .gitignore 也不会移除。
    这条直接问 git:实际跟踪清单里有没有它们。
    """
    tracked = _tracked(*[p.lstrip("/") for p in PERSONAL_PATHS])
    assert not tracked, (
        "个人内容已被代码仓跟踪(必须 git rm --cached 移除):\n  "
        + "\n  ".join(str(p.relative_to(REPO)) for p in tracked[:20]))


# 密钥形状:登录二维码也算凭据
#
# `lark-cli auth login` 会在**仓库根**生成 `lark-auth-qr.png` —— 扫一下就能登进
# 飞书账号,和密钥同级。而 .gitignore 里那批图片规则是 `raw/**/*.png`,**盖不到
# 仓库根**,于是它一直以未跟踪状态躺在那里,离入库只差一次 `git add -A`
# (2026-08-04 真机上就是这个状态)。

SECRET_PROBES = [".env", ".env.local", "probe.key", "probe.pem", "secrets.json",
                 "credentials.json", "token.json", "lark-auth-qr.png"]


def test_gitignore_still_shields_secret_shapes():
    """密钥形状必须被 git 忽略 —— **问 git 本身**,不读 .gitignore 文本。

    规则写成什么样不重要(`*.key` 还是 `**/*.key`、有没有被后面的 `!` 反选掉),
    *git 此刻到底忽不忽略*才是事实。探针路径不必真实存在:`git check-ignore`
    按路径名匹配规则,不看文件系统。
    """
    r = subprocess.run(["git", "check-ignore", "-v", *SECRET_PROBES],
                       cwd=str(REPO), capture_output=True, text=True)
    # 退出码 1 = 有路径没被忽略(正是我们要查的),不能当失败;2 才是 git 自己出错
    assert r.returncode in (0, 1), "git check-ignore 自身失败,门禁不能空转:" + r.stderr
    ignored = {line.rsplit("\t", 1)[-1] for line in r.stdout.splitlines() if "\t" in line}
    missing = [p for p in SECRET_PROBES if p not in ignored]
    assert not missing, (
        "这些密钥形状**没有**被 git 忽略,一次 `git add -A` 就会入库:\n  "
        + "\n  ".join(missing))
