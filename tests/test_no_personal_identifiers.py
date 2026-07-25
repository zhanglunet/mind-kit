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

REPO = Path(__file__).resolve().parent.parent


def _tracked(*globs):
    """已跟踪文件(只查入库的;工作区临时文件不管)。"""
    out = subprocess.run(["git", "-C", str(REPO), "ls-files", *globs],
                         capture_output=True, text=True).stdout.split("\n")
    return [REPO / p for p in out if p.strip()]


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


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
    """姓名/群名无形态可匹配,故断言相应脚本确实从 env 读取(字面值已移除)。"""
    expect = {
        "scripts/feishu-token-keepalive.sh": "MIND_FEISHU_OU",
        "scripts/build-kd-weekly.py": "MIND_KD_GROUP",
        "scripts/kd-weekly-sync.sh": "MIND_KD_GROUP",
        "scripts/feishu-fetch-chat-docs.py": "MIND_FEISHU_SELF",
    }
    missing = [f"{f} 应从 {var} 读取" for f, var in expect.items()
               if (REPO / f).exists() and var not in _read(REPO / f)]
    assert not missing, "身份类配置须走环境变量:\n  " + "\n  ".join(missing)


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
