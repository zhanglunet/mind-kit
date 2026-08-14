---
title: WorkBuddy 安装第二大脑
---

<div class="wb-hero">
  <div class="wb-eyebrow">WORKBUDDY · SECOND BRAIN</div>
  <h1>用 WorkBuddy，<br>装好你的<em>第二大脑</em>。</h1>
  <p>下载或从 SkillHub 安装技能包，WorkBuddy 负责本地安装公开仓（Vault-only）。飞书授权与内容同步属于完整发行包（邀请制），持有者沿用本页同一套提示词。</p>
</div>

[在 SkillHub 查看](https://skillhub.cn/skills/user_4c0191ff/mind) · [下载 ZIP](downloads/workbuddy-second-brain-skill-v1.0.1.zip)

<div class="wb-route" aria-label="三步安装流程">
  <div><span>01</span><strong>安装技能</strong><small>SkillHub 或 ZIP 导入</small></div>
  <b aria-hidden="true">→</b>
  <div><span>02</span><strong>本地安装</strong><small>公开包初始化 Vault</small></div>
  <b aria-hidden="true">→</b>
  <div><span>03</span><strong>授权同步</strong><small>仅完整发行包</small></div>
</div>

## 先分清两种发行包

- **公开仓 [mind-kit](https://github.com/zhanglunet/mind-kit)(人人可装)**:安装器是
  **Vault-only** —— 初始化本地知识库目录骨架与工具环境。**不含飞书同步连接器,
  不能执行飞书授权或内容同步**;安装器页面会明确提示这一点。
- **完整发行包(邀请制内测)**:含飞书云文档/知识库同步连接器。申请方式见
  [服务页](services.md)。持有者用同一个安装器,会看到 `127.0.0.1` 飞书授权页。

## 它能做什么

- 在 macOS、Linux、Windows 原生 PowerShell 上安装公开仓库 `mind-kit`,初始化本地 Vault;
- (完整发行包)引导你申请飞书最小权限,并在本机 `127.0.0.1` 页面完成授权;
- (完整发行包)按你确认的范围增量同步飞书文档与知识库;
- 先 dry-run,再编译为本地知识库,打开 [本地知识门户](http://127.0.0.1:8788/browse/index.html)。

## 开始前准备

你只需要:

- WorkBuddy 能在本机运行终端命令;
- Git、Python 3.9+;Node.js 和 npm 仅完整发行包(装 lark-cli)需要;
- 公开仓库:[mind-kit](https://github.com/zhanglunet/mind-kit);
- (仅完整发行包)飞书企业自建应用,或联系租户管理员协助授权。

Windows 10/11 使用 PowerShell 5.1+ 或 PowerShell 7,**不需要 WSL2**。完整技术说明见
[使用指南](usage.html)。

## 第二大脑 WorkBuddy 技能包：三步完成

### 1. 安装技能包

优先打开 [SkillHub 技能页面](https://skillhub.cn/skills/user_4c0191ff/mind) 安装；如果无法使用，下载本站 [ZIP 技能包](downloads/workbuddy-second-brain-skill-v1.0.1.zip)，进入 **专家·技能·连接器 → 技能 → 添加技能 → 上传技能**，然后在“我安装的”中启用“第二大脑安装技能”。

### 2. 交给 WorkBuddy 安装

把下面提示词复制给 WorkBuddy：

::: {.prompt-block data-label="提示词 1 · 安装并停在本地页面"}
```text
请使用“第二大脑安装与飞书备份技能”，安装公开仓库：
https://github.com/zhanglunet/mind-kit.git

先检查环境和目标目录，保留已有文件，不删除用户数据。
macOS/Linux 使用 ./install-second-brain；Windows 使用原生 PowerShell 的
install-second-brain.ps1，不需要 WSL2。

安装器打开 http://127.0.0.1 本地页面后请停下来，把地址告诉我。
公开包会显示 Vault-only 页面（不能同步飞书内容），这是预期行为；
只有完整发行包会出现飞书授权页。
不要索取、显示或保存 App Secret、access token、refresh token、二维码或飞书正文。
不要替我点击授权确认，也不要提交、推送或发布代码。
```
:::

公开包到这里已完成:Vault 目录骨架就绪,可以直接开始放入资料并编译
(Windows 编译命令是 `compile-second-brain.ps1`;macOS/Linux 是 `bash scripts/compile.sh`)。

### 3. 你授权，WorkBuddy 同步（仅完整发行包）

持有完整发行包时,在 `127.0.0.1` 授权页中：

1. 打开飞书开发者后台，创建企业自建应用；
2. 首次只申请文档和知识库的最小权限；
3. App Secret 只填入本地授权页，不要贴进 WorkBuddy；
4. 由你本人在飞书页面确认授权；
5. 回到 WorkBuddy，发送下面提示词。

::: {.prompt-block data-label="提示词 2 · 同步并验收"}
```text
我已在本地授权页面完成授权，并点击了“授权完成并开始同步”。

请继续观察同步直到完成，汇报同步模块、成功/失败数量、输出目录、增量状态和脱敏错误。
不要显示任何 Secret、token、二维码或私人飞书正文。
如果出现 missing_scope，只告诉我缺少的 scope，暂停等待我处理，不要自行扩大权限。
同步完成并由我确认结果后，先执行 dry-run，再完成首次编译。
```
:::

在公开包上发这条提示词会得到「当前公开发行包不含同步连接器」的报错——
这是边界设计,不是故障;申请完整发行包见[服务页](services.md)。

## 安全边界

- App Secret、access token、refresh token 和授权二维码不进入聊天；
- 公开包零凭证:Vault-only 安装不请求、不存储任何飞书凭证;
- 默认不读取聊天记录，不选择“全部权限”；
- 飞书内容写入你自己的本地 Vault，不上传到公开仓库；
- “同步完成”不代表内容会自动发送给大模型；是否编译、是否调用模型，由你决定；
- 这是一份个人可导入技能包，不是 WorkBuddy 官方“专家”或技能市场审核结果。

## 获取入口

| 入口 | 用途 |
|---|---|
| [SkillHub](https://skillhub.cn/skills/user_4c0191ff/mind) | 查看技能详情并安装 |
| [本站 ZIP](downloads/workbuddy-second-brain-skill-v1.0.1.zip) | 备用下载和手动导入 |
| [GitHub Releases](https://github.com/zhanglunet/mind-kit/releases) | 查看各版本与校验信息 |
| [源码仓库](https://github.com/zhanglunet/mind-kit) | 查看安装器和实现 |
| [服务页](services.md) | 申请含飞书同步的完整发行包 |

技能包不包含凭证、飞书内容或个人路径。
