---
title: 用 Codex 安装第二大脑并备份飞书
---

<div class="wb-hero">
  <div class="wb-eyebrow">CODEX GUIDED SETUP</div>
  <h1>让 Codex 安装第二大脑，<br>把飞书备份到自己的知识库</h1>
  <p>把公开仓库和下面的提示词交给 Codex：它负责检查环境、运行安装器和陪你验收；飞书权限、App Secret 和最终授权始终由你本人确认。</p>
  <div class="wb-actions">
<a class="wb-primary" href="#第一步准备仓库和提示词">从提示词开始</a>
<a class="wb-secondary" href="#第二步在本地完成飞书授权">先看授权边界</a>
  </div>
</div>

<div class="wb-route" aria-label="Codex 安装过程">
  <div><span>01</span><strong>Codex</strong><small>检查环境、克隆仓库</small></div>
  <b aria-hidden="true">→</b>
  <div><span>02</span><strong>你的浏览器</strong><small>申请权限、填写凭证</small></div>
  <b aria-hidden="true">→</b>
  <div><span>03</span><strong>Codex</strong><small>运行同步、检查备份</small></div>
  <b aria-hidden="true">→</b>
  <div><span>04</span><strong>你确认后</strong><small>首次编译、打开知识门户</small></div>
</div>

> **安全边界**：把公开仓库链接和提示词交给 Codex 即可；不要把飞书 App Secret、access token、refresh token、授权二维码或私人文档正文贴进聊天。凭证只填写在安装器打开的 `127.0.0.1` 本地页面中。

## 开始前准备

你需要：

- 一台由你控制的 macOS、Linux 或 Windows 10/11 电脑；
- 已安装 Git、Python 3.9+、Node.js 和 npm；
- 公开安装仓库：[https://github.com/zhanglunet/mind-kit](https://github.com/zhanglunet/mind-kit)；
- 飞书租户中创建企业自建应用的权限，或者能联系租户管理员；
- 约 15–30 分钟。首次同步内容较多时，需要更久，但可以增量续跑。

Windows 用户直接使用 PowerShell，不需要 WSL2：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
git clone https://github.com/zhanglunet/mind-kit.git
Set-Location .\mind-kit
.\install-second-brain.ps1
```

macOS/Linux 用户运行：

```bash
git clone https://github.com/zhanglunet/mind-kit.git
cd mind-kit
./install-second-brain
```

## 第一步：准备仓库和提示词

打开 Codex，把下面整段提示词发给它。Codex 可以使用你当前打开的仓库，也可以先从公开链接克隆；如果你使用的是自己的私有 fork，请把链接替换为你实际有权限访问的仓库。

::: {.prompt-block data-label="提示词 1 · 安装并停在授权页"}
```text
请在这台电脑上安装“第二大脑”，公开安装仓库是：
https://github.com/zhanglunet/mind-kit

请按以下要求执行：
1. 先检查目标目录是否已存在；保留已有文件和未提交改动，不覆盖、不删除用户数据。
2. macOS/Linux 运行 ./install-second-brain；Windows 使用原生 PowerShell 运行 powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install-second-brain.ps1，不使用 WSL。
3. 保持安装器进程运行，直到它打印 127.0.0.1 本地授权页面。
4. 把本地授权页地址告诉我，然后暂停，等待我在浏览器中操作。
5. 不要索取、显示、读取或保存飞书 App Secret、access token、refresh token、device code、授权二维码或私人文档正文。
6. 不要替我点击飞书授权确认，不要自行增加提示词未要求的权限。
7. 不要提交、推送、发布或部署代码。

授权页面出现后，只汇报：
- 仓库目录
- 127.0.0.1 授权页面地址
- 环境检查结果（不得包含凭证）
- “请在浏览器完成飞书授权，完成后回来告诉我”
```
:::

Codex 应该停在本地授权页，而不是替你输入 Secret 或确认授权。形如下面的地址只在你的电脑上有效，不要转发：

```text
http://127.0.0.1:随机端口/wizard?token=一次性随机值
```

## 第二步：在本地完成飞书授权

在 Codex 给出的本地页面中点击“打开飞书开发者后台”，或直接打开[飞书开发者后台](https://open.feishu.cn/app)。

1. 创建一个**企业自建应用**，例如“我的第二大脑”。
2. 进入 **开发配置 → 权限管理 → 开通权限**。
3. 默认申请文档和知识库的只读权限；云盘文件、聊天记录按实际需要再开通。
4. 在 **应用发布 → 版本管理与发布** 中创建并发布版本，公司租户可能需要管理员审核。
5. 在“凭证与基础信息”复制 App ID 和 App Secret，只填入本地 `127.0.0.1` 页面。
6. 在本地页生成授权链接或二维码，在飞书中核对应用名和权限后，由你本人点击确认。
7. 回到本地页点击“授权完成并开始同步”。

推荐的最小权限：

| 模块 | 权限 scope | 默认 | 说明 |
|---|---|---:|---|
| 云文档 | `drive:drive:readonly` | 是 | 读取你有权限访问的云文档 |
| 文档正文 | `docx:document:readonly` | 是 | 只读导出正文 |
| 知识库 | `wiki:wiki:readonly` | 是 | 读取你可访问的 Wiki 节点 |
| 云盘文件 | `search:docs:read`、`drive:file:download` | 否 | 只在需要备份普通文件时申请 |
| 聊天记录 | `im:chat:read` 等 | 否 | 涉及其他成员内容，非必要不要申请 |

飞书官方说明：[申请 API 权限](https://open.feishu.cn/document/server-docs/application-scope/introduction?lang=zh-CN)。不要为了省事选择“全部权限”。

## 第三步：让 Codex 运行备份并验收

完成授权后，把下面第二段提示词发回同一个 Codex 任务：

::: {.prompt-block data-label="提示词 2 · 同步飞书并验收"}
```text
我已在本地 127.0.0.1 页面完成飞书授权，并点击了“授权完成并开始同步”。

请继续：
1. 保持安装器进程运行，观察同步状态和终端日志，直到完成或出现明确错误。
2. 不要读取、回显或保存 App Secret、token、device code、二维码内容或私人文档正文。
3. 如果出现 missing_scope，只报告缺失的 scope 和原始 console_url，暂停等待我去飞书后台开通并发布新版本；不要自行扩大权限。
4. 同步完成后，检查文档、知识库输出目录、状态文件和非空 Markdown 样本。
5. 只汇报同步模块、成功/失败数量、输出目录、增量状态、脱敏后的错误和下一步建议。
6. 不要提交、推送、发布或上传我的飞书内容。
```
:::

备份验收至少应满足：

- 本地页面显示“同步完成”，不只是“授权成功”；
- 默认目录 `raw/private/feishu/` 下出现非空 Markdown；
- `_meta` 中存在增量状态，重复运行可以跳过未变化内容；
- Codex 的汇报中没有 Secret、token、二维码或聊天正文；
- 飞书个人内容没有进入 Git 提交、公开站点或发行方系统。

## 第四步：首次编译知识库

先让 Codex 完成脱敏和输出检查，再执行编译。

Windows 的编译入口是 `compile-second-brain.ps1`；macOS/Linux 使用 `scripts/compile.sh`。

Windows PowerShell：

```powershell
Set-Location .\mind-kit
.\compile-second-brain.ps1 -DryRun
.\compile-second-brain.ps1
```

macOS/Linux：

```bash
cd mind-kit
bash scripts/compile.sh --dry-run
bash scripts/compile.sh
```

编译产物写入你自己的私有 Vault，通常可从下面的本地地址查看：

```text
http://127.0.0.1:8788/browse/index.html
```

## 常见问题

| 现象 | 处理方式 |
|---|---|
| `missing_scope` | 按错误中的 `console_url` 开通缺失权限、发布新版本，再从本地页重新授权 |
| 授权链接过期 | 重新生成链接或二维码，不复用旧 URL、旧二维码或旧 device code |
| 文档有、知识库为空 | 检查 `wiki:wiki:readonly` 和当前账号的知识空间访问权限 |
| Windows 找不到命令 | 重新打开 PowerShell；确认 Python 安装时勾选了 Add Python to PATH |
| Codex 任务结束后同步中断 | 回仓库重新运行安装器，保持安装进程运行，再生成一次性授权 |

不要把 `raw/private/feishu/`、`_wiki/` 或个人 Vault 提交到公开仓库。完整安装和 Windows 原生 PowerShell 说明见[Workbuddy 指南](workbuddy.md)；两者使用同一安装器和同一授权边界。
