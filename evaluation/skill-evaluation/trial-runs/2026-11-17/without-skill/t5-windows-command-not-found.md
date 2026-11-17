<!-- trial-run: arm=without-skill task=t5-windows-command-not-found model=glm-5.3-flash temperature=0 run_at=2026-11-17T11:21:28.753176Z -->

这个问题很常见，通常是以下几个原因之一。按顺序排查：

## 1. 先重启终端（最常见）

安装完软件后，**已经打开的 PowerShell 窗口不会识别新程序**。把所有 PowerShell / VS Code / CMD 窗口全部关闭，重新打开再试。很多教程忘记提这一步。

## 2. 检查 PATH 环境变量

如果重启后还是不行，多半是安装目录没加入 PATH：

1. 按 `Win` 键，搜索“编辑系统环境变量” → 点击“环境变量”
2. 在“系统变量”或“用户变量”里找到 `Path`，点“编辑”
3. 把软件的安装目录（即包含 `.exe` 文件的那个文件夹）添加进去
4. 确定保存后，**重新打开 PowerShell** 再试

验证方法：用完整路径直接运行试试，比如：

```powershell
& "C:\Program Files\某软件\某软件.exe" --version
```

完整路径能跑通、短命令不行，就基本确定是 PATH 的问题。

## 3. 确认软件确实装上了

有些教程只讲怎么“用”，默认你已经装好。去安装目录确认 exe 文件是否存在，或者用诊断命令：

```powershell
Get-Command 命令名
```

## 4. 检查是不是教程环境不匹配

- 教程如果是给 **macOS / Linux** 写的，命令可能不一样，比如 `python3` 在 Windows 上一般是 `python`，`brew` 在 Windows 上不存在
- 如果教程明确是 Linux 环境，考虑装 **WSL**（Windows 子系统）再照着做

## 5. 看具体报错类型

- **“无法将 xxx 项识别为 cmdlet..."** → 上面 1~4 的问题
- **“无法加载文件 xxx，因为在此系统上禁止运行脚本”** → 这是执行策略问题，运行：
  ```powershell
  Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
  ```

---

方便的话告诉我：**你装的是什么软件、具体的报错信息是什么？** 我可以给你更针对性的步骤。
