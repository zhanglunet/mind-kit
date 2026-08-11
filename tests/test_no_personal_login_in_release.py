"""FR-DD-03:**依赖个人登录态的模块,不得进入任何发行集**(PRD D10)。

D10 的依据不是合规(`dws` 已确认是官方工具,D2 未被触碰),是**信任边界**:
服务化 PRD 的 G3 承诺订阅者「在自己机器上跑、接自己的账号」,运营者侧
**零凭证、零数据**。而这类模块要订阅者用,等于要他们交出**个人登录凭据** ——
与 G3 正面冲突,且没有任何技术手段能让它变得可接受。

**为什么必须是测试而不是文档条款**:本仓原则「Prompt 不是检查器」——
只有脚本能确定性执行的规则才算硬门禁。D10 写在 PRD 里只是尽力遵守;
写成这条测试,才是"忘了就红"。同型参照 FR-WX-01(微信线依赖门禁)。
"""
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DELETE = REPO / "publish" / "DELETE.txt"
KEEP_PRO = REPO / "publish" / "KEEP-pro.txt"

# 个人登录态的判别特征:调用官方 CLI `dws`(它以个人身份登录,非应用鉴权)
PERSONAL_LOGIN_MARKERS = ('"dws"', "'dws'", "[\"dws\"]", "dws minutes", "dws ")


def _uses_personal_login(text: str) -> bool:
    return any(m in text for m in PERSONAL_LOGIN_MARKERS)


def test_detector_recognises_a_personal_login_call():
    """先钉住**探测器本身**能用 —— 否则真文件落地时门禁静默放行。

    (恒绿的门禁等于没有门禁,还更坏:它让人以为有人在看着。)
    """
    assert _uses_personal_login('subprocess.run(["dws", "minutes", "+detail"])')
    assert _uses_personal_login('cmd = ["dws"] + args')
    assert not _uses_personal_login('subprocess.run(["git", "status"])')
    assert not _uses_personal_login("# 说明:窗口宽度 dwsize 之类的无关词")


def _tracked_scripts():
    out = subprocess.run(
        ["git", "-C", str(REPO), "-c", "core.quotepath=false",
         "ls-files", "-z", "--", "scripts/"],
        capture_output=True, text=True, check=True).stdout
    return [p for p in out.split("\0") if p]


def _personal_login_scripts():
    hits = []
    for p in _tracked_scripts():
        f = REPO / p
        if not f.is_file():
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if _uses_personal_login(text):
            hits.append(p)
    return hits


def _covered(path: str, listed) -> bool:
    return any(path == d or path.startswith(d.rstrip("/") + "/") for d in listed)


def _entries(f: Path):
    if not f.exists():
        return set()
    return {ln.split("#")[0].strip() for ln in f.read_text(encoding="utf-8").splitlines()
            if ln.split("#")[0].strip()}


def test_personal_login_scripts_never_reach_the_public_kit():
    leaked = [p for p in _personal_login_scripts() if not _covered(p, _entries(DELETE))]
    assert not leaked, (
        "这些脚本依赖**个人登录态**,却没被 publish/DELETE.txt 覆盖,会随下次发版公开:\n  "
        + "\n  ".join(leaked) + "\n见 PRD D10 / FR-DD-03。")


def test_personal_login_scripts_never_reach_the_private_release_set():
    """mind-pro(私有发行仓)同样不许收 —— D10 管的是**任何**发行集,不只公开版。"""
    keep = _entries(KEEP_PRO)
    bad = [p for p in _personal_login_scripts() if _covered(p, keep)]
    assert not bad, ("这些依赖个人登录态的脚本出现在 publish/KEEP-pro.txt 白名单里:\n  "
                     + "\n  ".join(bad) + "\n见 PRD D10。")
