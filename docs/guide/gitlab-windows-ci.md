---
title: GitLab Windows 原生 CI
---

# GitLab Windows 原生 CI

Windows 安装器和编译入口使用 GitLab CI/CD 的自托管 Windows Runner 验证，不使用
GitHub Actions 的 `windows-latest`。

## Runner 要求

- Windows 10/11 或 Windows Server；
- GitLab Runner 使用 Shell executor；
- PowerShell 5.1+ 或 PowerShell 7；
- 安装 Git、Python 3 和 PowerShell，并让 Runner 服务账号可从 `PATH` 找到它们；
- Runner 标签同时包含 `windows` 和 `powershell`，与 `.gitlab-ci.yml` 一致。

在 GitLab 项目的 **Settings → CI/CD → Runners** 创建项目 Runner，复制 GitLab 显示的
认证 token，再按 GitLab 官方 Windows 安装和注册说明把 Runner 安装为服务。注册时选择
`shell` executor，并设置上述标签。不要把 Runner token 提交到仓库或粘贴进 issue。

## 流水线做什么

`windows-native` job 会在真正的 Windows PowerShell 环境中：

1. 创建 `.venv` 并安装依赖；
2. 运行 `install-second-brain.ps1 -SelfCheck`；
3. 运行 `compile-second-brain.ps1 -SelfCheck`；
4. 执行安装器、跨平台入口和本地服务的回归测试。

如果 job 一直处于 pending，先检查项目是否有在线 Runner，以及它是否同时具备
`windows`、`powershell` 两个标签。Linux 回归测试仍由同一个 `.gitlab-ci.yml` 的
`linux-tests` job 运行。
