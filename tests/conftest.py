"""全套件共享夹具:把「跑测试的这台机器恰好装了/配了什么」隔离掉。

本仓的测试大量用 subprocess 起 git 和 shell 脚本,子进程默认继承 os.environ。
个人机器上的**全局 git 配置**于是会渗进来:`commit.gpgsign=true`(签名密钥在
另一台机器上就直接 commit 失败)、全局 `core.hooksPath`(把仓库自己的钩子顶掉)、
`init.templateDir`、`core.quotepath`……开发容器与刚装好的 VM 都是干净配置,
用户的 macOS 笔记本不是 —— 同一份代码,三台机器三种结果。

`GIT_CONFIG_GLOBAL` / `GIT_CONFIG_SYSTEM` 指向 /dev/null(git ≥ 2.32)即可让
所有 git 子进程只认仓库级配置。身份也一并钉死,免得依赖 ambient user.name。
"""
import os

import pytest


@pytest.fixture(autouse=True, scope="session")
def _isolate_git_config():
    saved = {k: os.environ.get(k) for k in (
        "GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM",
        "GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL",
        "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL",
    )}
    os.environ.update({
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_AUTHOR_NAME": "mind-tests",
        "GIT_AUTHOR_EMAIL": "tests@example.invalid",
        "GIT_COMMITTER_NAME": "mind-tests",
        "GIT_COMMITTER_EMAIL": "tests@example.invalid",
    })
    yield
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
