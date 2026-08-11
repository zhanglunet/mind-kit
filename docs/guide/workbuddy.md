---
title: 用 Workbuddy 安装第二大脑
---

<div class="wb-hero">
  <div class="wb-eyebrow">WORKBUDDY GUIDED SETUP</div>
  <h1>把安装交给 Workbuddy，<br>把授权留给你自己</h1>
  <p>复制第一段提示词，让 Workbuddy 准备本地环境；在浏览器里亲自完成飞书权限与授权；同步验收后，再由你决定是否付费调用模型开始首次编译。</p>
  <div class="wb-actions">
<a class="wb-primary" href="#第一步把这段提示词交给-workbuddy">从第一段提示词开始</a>
<a class="wb-secondary" href="#飞书权限申请清单">先看权限清单</a>
  </div>
</div>

<div class="wb-route" aria-label="安装过程">
  <div><span>01</span><strong>Workbuddy</strong><small>克隆、安装、启动向导</small></div>
  <b aria-hidden="true">→</b>
  <div><span>02</span><strong>你的浏览器</strong><small>申请权限、输入凭证、扫码</small></div>
  <b aria-hidden="true">→</b>
  <div><span>03</span><strong>Workbuddy</strong><small>观察同步、排错、验收</small></div>
  <b aria-hidden="true">→</b>
  <div><span>04</span><strong>你确认后</strong><small>首次编译、打开本地知识门户</small></div>
</div>

> **最重要的安全边界**：完整仓库链接可以放进提示词；App Secret、access token、
> refresh token 和授权二维码都不要贴进 Workbuddy 聊天。App Secret 只填在安装器打开的
> `127.0.0.1` 本地网页中，由它通过 stdin 交给 lark-cli，再保存到系统钥匙串。

## 开始前准备

你需要：

- 一台由你控制的 macOS、Linux，或 Windows 10/11 电脑，Workbuddy 能在这台电脑上运行终端命令；
- Windows 直接使用 **PowerShell 5.1+ 或 PowerShell 7**，不需要 WSL2；
- 公开仓库链接 [https://github.com/zhanglunet/mind-kit](https://github.com/zhanglunet/mind-kit)；
- 飞书租户中创建企业自建应用的权限，或者能联系到租户管理员；
- 约 15–30 分钟。文档很多时，首次同步会更久，但中断后可以增量续跑。

不需要把 GitHub token、飞书 App Secret 或任何 API Key 发给本页面、Workbuddy 或发行方。

## “完整仓库链接”填什么

直接使用公开 HTTPS 克隆地址：

```text
https://github.com/zhanglunet/mind-kit.git
```

公开仓已经包含 macOS/Linux 启动器、原生 PowerShell 启动器、飞书最小权限授权页，以及
文档、知识库、云盘文件、群聊和单聊同步模块。**不需要 GitHub 登录、私有仓邀请或访问令牌。**

## 第一步：把这段提示词交给 Workbuddy

下面已经填好公开仓库地址，整段复制即可。

::: {.prompt-block data-label="提示词 1 · 安装并停在授权页"}
```text
请在这台电脑上安装“第二大脑”，完整仓库链接是：
https://github.com/zhanglunet/mind-kit.git

请按以下要求执行：
1. 先检查目标目录是否已存在；保留已有文件和未提交改动，不覆盖、不删除用户数据。
2. 克隆或更新公开仓库，阅读仓库内安装说明。macOS/Linux 在仓库根目录运行 ./install-second-brain；Windows 原生 PowerShell 运行 powershell -ExecutionPolicy Bypass -File .\install-second-brain.ps1。
3. 保持安装器进程持续运行，不要因为命令暂时没有输出而结束它。
4. 安装器出现 127.0.0.1 本地授权页面后，把页面地址告诉我，并停下来等我操作。
5. 不要在聊天中索取、显示或保存飞书 App Secret、access token、refresh token、device code 或授权二维码。
6. 不要替我点击飞书授权确认，不要申请页面未列出的额外权限。
7. 暂时不要提交、推送、发布或部署任何代码。

当本地授权页面已可打开时，只需回复：
- 仓库所在目录
- 本地授权页面地址
- 环境检查结果（不得包含凭证）
- “请在浏览器完成授权，完成后回来告诉我”
```
:::

正常情况下，Workbuddy 最后会给你一个类似下面的地址：

```text
http://127.0.0.1:随机端口/wizard?token=一次性随机值
```

这个 URL 只在你的电脑上有效。不要把它转发给别人，也不要删改其中的 token。

### Workbuddy 此时应该做到什么

<div class="wb-checkgrid">
  <div><strong>✓ 已完成</strong><span>仓库就绪、Vault 初始化、依赖安装、授权页启动</span></div>
  <div><strong>⏸ 应暂停</strong><span>把本地页面交给你，不接触 App Secret，不代替你确认授权</span></div>
  <div><strong>✗ 不应发生</strong><span>把 Secret 写入命令行、聊天、日志、仓库或截图</span></div>
</div>

## 第二步：申请飞书权限

在本地授权页点击“打开飞书开发者后台”，或直接进入
[飞书开发者后台](https://open.feishu.cn/app)。

1. 创建一个**企业自建应用**，建议名称写“我的第二大脑”。
2. 打开 **开发配置 → 权限管理 → 开通权限**。
3. 按下面清单申请权限。默认只选文档与知识库；云盘文件、聊天记录按需要选择。
4. 打开 **应用发布 → 版本管理与发布**，创建版本并发布。公司租户可能需要管理员审核。
5. 在“凭证与基础信息”复制 App ID 和 App Secret，准备填入本地授权页。

飞书官方流程说明：[申请 API 权限](https://open.feishu.cn/document/server-docs/application-scope/introduction?lang=zh-CN)。

### 飞书权限申请清单

| 模块 | 权限 scope | 是否默认 | 数据边界 |
|---|---|---:|---|
| 我的云文档 | `drive:drive:readonly` | 是 | 枚举我拥有的云文档 |
| 文档正文 | `docx:document:readonly` | 是 | 只读导出为 Markdown |
| 知识库 | `wiki:wiki:readonly` | 是 | 读取我可访问的 Wiki 节点与正文 |
| 云盘文件 | `search:docs:read`、`drive:file:download` | 否 | 下载我拥有的普通文件 |
| 群聊与单聊 | `im:chat:read`、`im:message.group_msg:get_as_user`、`im:message.p2p_msg:get_as_user` | 否 | 包含他人消息，通常需要管理员审批 |

::: {.wb-callout .warn}
**不要为了省事选择“全部权限”。** 安装器使用 `--scope` 发起最小权限授权；飞书后台的应用权限和用户扫码授权两层都要满足。聊天记录涉及其他成员内容，不需要就不要勾选。
:::

## 第三步：在本地页面完成授权

回到 Workbuddy 给出的 `127.0.0.1` 页面，依次操作：

<div class="wb-steps">
  <div><span>1</span><div><strong>选择同步范围</strong><p>默认文档和知识库；只有确实需要时才勾选云盘文件或聊天记录。</p></div></div>
  <div><span>2</span><div><strong>填写 App ID 与 App Secret</strong><p>点击“保存到系统钥匙串”。Secret 不会进入聊天或仓库。</p></div></div>
  <div><span>3</span><div><strong>生成授权链接和二维码</strong><p>页面会显示原始授权链接及二维码。打开链接或扫码。</p></div></div>
  <div><span>4</span><div><strong>在飞书确认授权</strong><p>核对应用名和权限范围后，由你本人点击确认。</p></div></div>
  <div><span>5</span><div><strong>回到本地页开始同步</strong><p>点击“授权完成并开始同步”。安装器在线校验 token，先冒烟，再自动增量同步。</p></div></div>
</div>

授权链接过期时，回到本地页面重新点击“生成授权链接和二维码”。不要复用旧 URL、旧二维码或旧 device code。

## 第四步：回到 Workbuddy 继续

当本地页面显示“正在同步”或“同步完成”后，把下面第二段提示词交给**同一个 Workbuddy 任务**。

::: {.prompt-block data-label="提示词 2 · 监控同步并验收"}
```text
我已在本地授权页面完成飞书授权，并点击了“授权完成并开始同步”。

请继续处理：
1. 保持 install-second-brain 安装器进程运行，观察页面状态和终端日志直到完成或出现明确错误。
2. 不要读取、回显或保存任何 App Secret、token、device code、二维码内容。
3. 如果提示 missing_scope，只报告缺失的 scope 和原始 console_url，等我去飞书后台开通并发布新版本；不要自行扩大权限。
4. 如果授权链接过期，让我回到本地页面重新生成，不要复用旧链接。
5. 同步成功后，检查文档和知识库输出目录、状态文件和非空 Markdown 样本；若我勾选了可选模块，也分别检查。
6. 最终只汇报：同步模块、成功/失败数量、输出目录、增量状态、脱敏后的错误和下一步建议。
7. 不要提交、推送、发布或上传我的飞书内容。
```
:::

### 成功验收标准

- 本地授权页状态为“同步完成”，而不是只显示“授权成功”；
- token 在线校验通过，身份为 user；bot 身份看不到你的个人云盘；
- 默认目录 `raw/private/feishu/` 下出现非空 Markdown；
- `_meta` 中存在增量状态，重新运行时未变化内容会跳过；
- Workbuddy 的汇报中没有 App Secret、token、device code 或聊天正文；
- 个人飞书内容没有进入 Git 提交、公开站点或发行方系统。

## 常见卡点

| 现象 | 原因 | 怎么处理 |
|---|---|---|
| `missing_scope` / `need_user_authorization` | 后台权限或用户授权缺一层 | 使用错误中原始 `console_url`，开通缺失 scope，发布新版本，再从本地页重新授权 |
| 授权链接已过期 | device flow 有时效 | 重新生成链接和二维码；不要复用旧值 |
| 授权成功但 token 校验失败 | 授权尚未完成收口或 profile 不一致 | 保持原安装任务，回本地页重试；让 Workbuddy 只做脱敏诊断 |
| 文档有、知识库为空 | 应用未开 Wiki 权限，或账号不可访问对应空间 | 检查 `wiki:wiki:readonly` 和当前飞书账号的空间权限 |
| 手动同步正常，定时同步写入失败 | macOS 对 CloudStorage 的权限限制 | 按错误提示给定时进程授权，或把 `MIND_FEISHU_HOME` 改到普通本地目录 |
| Workbuddy 任务被关闭 | 安装器进程随任务结束 | 回仓库重新运行安装器；Windows 用 `.\install-second-brain.ps1`，macOS/Linux 用 `./install-second-brain` |

## 隐私与退出

- 凭证：由 lark-cli 保存在你自己的系统钥匙串；发行方不接触。
- 数据：保存在你自己的 `raw/private/feishu/`；默认被 Git 忽略。
- 退出：停止定时任务、删除本地冷存，并在飞书授权管理页撤销服务端授权或删除自建应用。
- `lark-cli auth logout` 只清除当前机器登录态，不等于撤销飞书服务端授权。

## 第五步：开始首次编译并打开指南

“同步完成”只代表飞书内容已安全落到本地冷存，**不会自动把全部飞书内容送给大模型**。
这是刻意的隐私和费用边界。先挑选值得进入知识体系的 Markdown，复制到
`raw/clippings/`；需要深度处理、希望先审阅的材料放进 `raw/todo/`。

首次编译会调用你配置的大模型并可能产生费用。先让 Workbuddy 只做估算：

```bash
# macOS / Linux
bash scripts/compile.sh --dry-run

# Windows PowerShell
.\compile-second-brain.ps1 -DryRun
```

确认范围、模型和预估费用后，再运行：

```bash
# macOS / Linux
bash scripts/compile.sh
python3 scripts/brain-server.py

# Windows PowerShell
.\compile-second-brain.ps1
.\.venv\Scripts\python.exe scripts\brain-server.py
```

然后打开本地私密知识门户：
[http://127.0.0.1:8788/browse/index.html](http://127.0.0.1:8788/browse/index.html)。
日常摄入、查询、健检和全量更新见本站[使用指南](usage.html)。

::: {.prompt-block data-label="提示词 3 · 经我确认后首次编译"}
```text
飞书同步已经验收完成。请先不要直接编译全部冷存内容。

请继续：
1. 说明 raw/private/feishu 是私密冷存，不是默认编译源。
2. 帮我从待处理材料中挑选本次要编译的文件；未经我确认，不要批量复制飞书全库。
3. 把我确认的材料放入 raw/clippings/；macOS/Linux 先运行 bash scripts/compile.sh --dry-run，Windows PowerShell 先运行 .\compile-second-brain.ps1 -DryRun。
4. 汇报本次范围、模型和费用风险，停下来等我明确回复“可以编译”。
5. 得到确认后按当前操作系统运行正式编译入口；完成后启动 scripts/brain-server.py。
6. 给我本地入口 http://127.0.0.1:8788/browse/index.html 和在线使用指南 https://aip.cab/usage。
7. 不提交、推送或上传 raw/private、raw、_wiki、material、writing 中的个人内容。
```
:::

## 一句话记住整个过程

<div class="wb-summary"><strong>提示词 1 安装</strong><span>→</span><strong>浏览器里由你授权</strong><span>→</span><strong>提示词 2 同步验收</strong><span>→</span><strong>提示词 3 经你确认后编译</strong></div>

<script>
document.querySelectorAll('.prompt-block').forEach(function(block) {
  var pre = block.querySelector('pre');
  if (!pre) return;
  var button = document.createElement('button');
  button.type = 'button';
  button.className = 'wb-copy';
  button.textContent = '复制提示词';
  button.setAttribute('aria-label', '复制这段 Workbuddy 提示词');
  button.addEventListener('click', function() {
    navigator.clipboard.writeText(pre.innerText).then(function() {
      button.textContent = '已复制 ✓';
      setTimeout(function() { button.textContent = '复制提示词'; }, 1800);
    });
  });
  block.insertBefore(button, pre);
});
</script>
