"""Public, credential-free argv construction for ``lark-cli``.

单一语义来源:私有同步层委托本模块,argv 边界行为只在这里定义一次
(行为契约见 tests/test_lark_cli_argv.py;委托关系由私有侧测试锁定)。
"""

import os
import shutil
from typing import List, Optional


def lark_argv(args: List[str], profile: Optional[str] = None) -> List[str]:
    """Build a lark-cli command while optionally selecting a profile.

    profile=None 沿用 MIND_LARK_PROFILE;显式传值由调用方选择 profile,
    空串/纯空白表示明确不注入。全局旗标始终在子命令之前。
    """
    executable = shutil.which("lark-cli") or "lark-cli"
    if os.name == "nt":
        executable = (
            shutil.which("lark-cli.cmd")
            or shutil.which("lark-cli.exe")
            or executable
        )
    if profile is None:
        profile = os.environ.get("MIND_LARK_PROFILE", "")
    selected = str(profile).strip()
    prefix = ["--profile", selected] if selected else []
    return [executable, *prefix, *args]
