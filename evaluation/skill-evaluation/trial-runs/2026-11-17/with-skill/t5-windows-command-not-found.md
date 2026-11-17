<!-- trial-run: arm=with-skill task=t5-windows-command-not-found model=glm-5.3-flash temperature=0 run_at=2026-11-17T11:17:35.547655Z -->

**当前阶段**：Windows 环境检查与安装，下一步由你操作。

先告诉我两件事，我好帮你精确定位：

1. **具体是哪个命令报错？** 是 `git`、`python`，还是 `.\install-second-brain.ps1`？把报错原文贴出来（可脱敏）。
2. **你拿到的是哪种发行包？** 公开仓 mind-kit（人人可装）还是完整发行包（内测）？这决定后面能否做飞书同步，但安装步骤两者相同。

在等你回复前，先按最常见的三种情况自查：

**情况一：`git` 无法识别**

- Git 没安装或没加入 PATH。到 git-scm.com 下载 Git for Windows 安装，安装时保持默认 PATH 选项即可。

**情况二：`python` 无法识别**

- 最常见原因：安装 Python 时**没勾选 Add Python to PATH**。
- 解决：重新运行 Python 安装程序（需要 3.9+），在安装首页**底部勾选 "Add Python to PATH"** 再装。
- 提示：公开版 Vault-only 安装不需要 Node.js 和 npm，只有完整发行包才需要。

**情况三：找不到 `install-second-brain.ps1`**

- 说明当前目录不对，先进入仓库目录：
  ```powershell
  Set-Location .\mind-kit
  ```

**关键一步：完全关闭 PowerShell，重新打开一个新窗口**。旧窗口读不到新装的 PATH，装完不重开照样报找不到命令。

重开后先验证环境：

```powershell
git --version
python --version
```

两者都有版本号输出后，再按教程执行。注意**每次新开 PowerShell 都要重新执行第一行**：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
git clone https://github.com/zhanglunet/mind-kit.git
Set-Location .\mind-kit
.\install-second-brain.ps1
```

顺带区分一个易混淆的错误：如果报的是「禁止运行脚本」而不是「找不到命令」，那是执行策略问题——先跑第一行 `Set-ExecutionPolicy` 即可，不是环境坏了。

告诉我具体报错信息和发行包类型，我继续帮你处理。
