# tests/test_larklib.py — scripts/larklib.py 的契约测试 + 调用点卫生门禁。
#
# 多账号前提(实测结论):lark-cli 有 profile 体系,但**不读环境变量**
# (LARK_CLI_PROFILE/LARK_PROFILE 实测无效),只能显式传 `--profile`。
# 所以同步脚本必须经过 larklib 注入,任何脚本绕过去直接调,多账号就静默漏数据。
import os
import re
from pathlib import Path

import pytest

import larklib

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "scripts"


def test_argv_plain_without_env(monkeypatch):
    monkeypatch.delenv("MIND_LARK_PROFILE", raising=False)
    assert larklib.lark_argv(["im", "+chat-search"]) == ["lark-cli", "im", "+chat-search"]


def test_argv_injects_profile_when_env_set(monkeypatch):
    monkeypatch.setenv("MIND_LARK_PROFILE", "acct2")
    assert larklib.lark_argv(["im", "+chat-search"]) == \
        ["lark-cli", "--profile", "acct2", "im", "+chat-search"]


def test_feishu_root_default_and_override(monkeypatch, tmp_path):
    monkeypatch.delenv("MIND_FEISHU_HOME", raising=False)
    assert larklib.feishu_root(tmp_path) == tmp_path / "raw" / "private" / "feishu"
    monkeypatch.setenv("MIND_FEISHU_HOME", str(tmp_path / "feishu-acct2"))
    assert larklib.feishu_root(tmp_path) == tmp_path / "feishu-acct2"


# —— 卫生门禁:任何脚本调 lark-cli 必须经 larklib(例外只有 larklib 自己与 shell 包装)——

# 目前无豁免:唯一直接调 lark-cli 的 shell(feishu-token-keepalive.sh)已自带注入。
EXEMPT_SH: set = set()


def test_no_script_calls_lark_cli_directly():
    """scripts/*.py 里出现 "lark-cli" 字面量的文件必须 import larklib。

    否则新脚本/新调用点绕开注入,MIND_LARK_PROFILE 对它无效——
    账号 B 的 cron 会静默读到账号 A 的数据(最难发现的那种错)。
    """
    offenders = []
    for f in sorted(SCRIPTS.glob("*.py")):
        if f.name == "larklib.py":
            continue
        src = f.read_text(encoding="utf-8")
        if '"lark-cli"' in src and "import larklib" not in src:
            offenders.append(f.name)
    assert not offenders, "这些脚本直接调 lark-cli 而未走 larklib:" + ", ".join(offenders)


def test_explicit_profile_overrides_environment(monkeypatch):
    monkeypatch.setenv("MIND_LARK_PROFILE", "from-env")
    assert larklib.lark_argv(["auth", "status"], profile="chosen") == [
        "lark-cli", "--profile", "chosen", "auth", "status"
    ]
    assert larklib.lark_argv(["config", "show"], profile="") == [
        "lark-cli", "config", "show"
    ]


def test_shell_wrappers_respect_profile_env():
    """shell 包装脚本若**真实调用** lark-cli,必须有 profile 注入(豁免清单即凭证)。

    注释/说明文字里的提及不算;`command -v lark-cli` 这类探测也不算。
    """
    call_re = re.compile(r"(^|\||;|&&|\$\()\s*lark-cli\s")
    for sh in sorted(SCRIPTS.glob("*.sh")):
        code = "\n".join(l for l in sh.read_text(encoding="utf-8").splitlines()
                         if not l.lstrip().startswith("#"))
        if not call_re.search(code):
            continue
        assert sh.name in EXEMPT_SH or "MIND_LARK_PROFILE" in code, \
            f"{sh.name} 直接调 lark-cli 但无 MIND_LARK_PROFILE 注入,也不在豁免清单"
