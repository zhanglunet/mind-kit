---
title: 用 AI Agent 安装
---

# 用 AI Agent 安装第二大脑

> **一句话**:把[第 2 节那段提示词](#2-安装提示词整段复制)整段丢给任意编码 agent,
> 它替你走完《[安装指南](install.md)》的六步;你只负责三件**它不该替你做**的事 ——
> **填密钥、批准花钱的那一步、验收**。

> **只想赶紧装上、不看解释?** → [一键安装:一段提示词装好](quick-install.md)。
> 本页是它的完整版:每条约束为什么这么写、装完怎么配、编译机制怎么转。

## 0. 这页和《安装指南》的关系

| | 《[安装指南](install.md)》 | 本页 |
|---|---|---|
| 面向 | 人手动执行 | 交给编码 agent 执行 |
| 地位 | **权威步骤** | 执行方法 + 一段可粘贴的提示词 |
| 冲突时 | **以它为准** | 听它的 |

本页**不重复**安装指南的细节(为什么 `sage-wiki` 要 ≥ 0.2.6、后端 profile 怎么配),
只讲**怎么把那些步骤安全地交出去**,以及交出去之后你要盯什么。

> **为什么值得用 agent 装**:这套骨架的安装不是"下一步下一步",而是
> 「装引擎 → 验引擎版本行为 → 配密钥 → 建内容库软链 → 验连通 → 首次编译」六段,
> 每段都有一个**沉默失败**的坑(见第 8 节)。agent 擅长的正是**逐条跑、逐条贴输出**;
> 它不擅长的是判断"这个失败要不要继续"——所以提示词里把那些判断点**全部交还给你**。

## 1. 前置:agent 之外你得先有的东西

agent 能替你装依赖,但下面这些要么得你本人操作,要么得先存在:

| 项 | 谁来做 | 说明 |
|---|---|---|
| Git / Go / Node.js / Python 3.9+ | 你(agent 给命令) | 装系统级运行时通常要 sudo,别让 agent 代劳 |
| **一个大模型 API Key** | **只有你** | GLM(默认)/ DeepSeek / Kimi 任一;写进 shell profile,**不落任何仓库文件** |
| Obsidian | 你 | 桌面端,安装完再把 vault 目录打开即可 |
| 一个空目录 + 已 clone 的仓库 | 你 | agent 需要在**仓库根**启动,否则它看不到 `config.yaml` 与 `CLAUDE.md` |

## 2. 安装提示词(整段复制)

在**仓库根目录**启动你的编码 agent,把下面整段作为第一条消息发给它:

```text
你是我的安装助手。目标:在这台机器上把「第二大脑」骨架跑起来。
权威步骤是仓库里的 docs/guide/install.md —— 以它为准,本提示词与它冲突时听它的。

硬约束(先读完再动手):
1. 密钥你不碰。需要 API key 时停下来告诉我该 export 哪个环境变量,由我自己填。
   不要把密钥写进任何文件、不要读我的 shell profile、不要回显任何密钥值。
2. 花钱的一步必须先问。`bash scripts/compile.sh` 会调用大模型 API 按量计费;
   在我明确说"可以编译"之前不要运行它。
3. 已初始化的仓库里永远不要跑 `sage-wiki init`。它只用于全新目录。
4. 不要替我 commit 或 push。你可以改文件,提交由我决定。
5. 每步留证据:每执行一条命令,把真实输出贴出来再下结论。
   命令失败就停下来报错,不要自己绕过去、不要"应该没问题"。
6. 不确定就问。不要猜路径、不要猜版本号、不要用推测代替实际输出。

按下面的顺序做。每完成一步,报告「做了什么 / 实际输出 / 通过与否」:

第 0 步 只读盘点(先别装任何东西)
  - 报告 git / go / node / python3 / pandoc 的实际版本(没有就说没有)
  - `pwd` 与 `ls`,确认当前在仓库根(应能看到 config.yaml、CLAUDE.md、scripts/)
  - 报告 `command -v sage-wiki` 与 `command -v claude` 的结果
  - 盘点完停下来等我确认,再进入第 1 步

第 1 步 脚本依赖
  - 缺 Go / Node / Python 的,给出这台机器上对应的安装命令交给我执行,你不要装
  - `pip install -r requirements.txt`

第 2 步 编译引擎 sage-wiki
  - `go install github.com/xoai/sage-wiki/cmd/sage-wiki@latest`
    (主包在 cmd/ 下;路径漏了会报 no non-test Go files)
  - 确认 `export PATH="$HOME/go/bin:$PATH"` 已在我的 shell profile 里
  - 跑一遍 docs/guide/install.md §3.1 的行为验证,确认版本 ≥ 0.2.6:
    它必须"追加" .sage/ 而不是重写 .gitignore,且 .manifest.json 不被清空。
    任一项不符,告诉我要升级,不要继续。

第 3 步 API Key(你只给指令,不要执行)
  - 告诉我该 export 哪个变量(默认后端 GLM → GLM_API_KEY)
  - 我说"配好了"之后再往下

第 4 步 内容库与软链
  - `bash scripts/init-vault.sh --dry-run` 先把计划给我看
  - 我同意后再 `bash scripts/init-vault.sh`
  - `bash scripts/vault.sh repo` 应打印内容库路径;
    若打印的是代码库路径就停下来 —— 软链没建成,之后提交会把个人内容写进代码库

第 5 步 连通性
  - `sage-wiki doctor`,把输出原样贴给我

第 6 步 首次编译(要我明确同意才做)
  - 我同意后 `bash scripts/compile.sh`
  - 跑完报告:_wiki/ 下生成了什么、index.md 是否更新、
    lint 报告落在哪个文件、整体退出码是多少

收尾:按 install.md 的「首周验收清单」逐条核对,逐条说通过还是没通过。
没通过的照实说,不要粉饰。
```

## 3. 这段提示词为什么这么写

每一条硬约束都对着一个**真实会发生的坏结果**,不是客套话:

| 约束 | 不写会怎样 |
|---|---|
| **密钥你不碰** | agent 为了"帮你配好"会把 key 写进文件或回显到对话里 —— 密钥一旦进了聊天记录/日志,就得当作已泄露处理 |
| **编译要先问** | `compile.sh` 按量计费。空的 `.manifest.json` 会让引擎**把整个知识库从头重编**(全额 API 费用) |
| **不许跑 `sage-wiki init`** | 0.2.6 之前它会把 `.gitignore` 整个改写成一行。**没有任何东西会重建它** —— 密钥形状与个人内容的忽略规则一起消失,可能很久没人发现 |
| **不许替你 commit** | 内容库/代码库分家(见第 6 节)。提交到错的那个库,个人内容就进了代码仓的历史 |
| **每步留证据** | "应该装好了"和"装好了"在终端里长得一样。**只有真实输出算数** |
| **第 0 步只读盘点** | 让 agent 先看清环境再动手;也给你一个"现在还什么都没改"的中断点 |

> **一条建议**:开 agent 的**逐步确认/审批模式**,别开全自动。
> 这套安装里有三处**不可逆或要花钱**的动作(建软链、写 profile、首次编译),
> 全自动模式下它们会一口气过去。

## 4. 各家 agent 怎么起

### 4.1 通用做法(任意编码 agent)

1. `cd` 到**仓库根目录**再启动 agent —— 它的工作目录决定了它能不能看到
   `config.yaml`、`CLAUDE.md`、`scripts/`
2. 把第 2 节那段提示词**整段**作为第一条消息发过去(别拆开发,约束和步骤要一起进上下文)
3. 打开**逐步确认**模式;拒绝任何"要不要我顺手 commit"的提议
4. 每一步都要它**贴真实输出**;它说"完成"而没有输出时,让它重跑并贴出来

这套做法与具体是哪个 agent 无关 —— 提示词里没有任何一家专属的语法。

### 4.2 Claude Code

```bash
npm install -g @anthropic-ai/claude-code
cd /path/to/mind
claude
```

仓库根自带 **`CLAUDE.md`**(权责边界"宪法"),Claude Code 会自动读它 ——
所以它天然知道哪些目录不能碰(`_wiki/` 的引擎领地、`raw/private/` 等)。
默认就是逐条请求权限,符合第 3 节的建议。

### 4.3 Codex

```bash
cd /path/to/mind
codex
```

Codex 读的是 **`AGENTS.md`**,而本仓目前**只有 `CLAUDE.md`**。
两种做法都行:

- 在提示词开头补一句「**先读 `CLAUDE.md`,把它当作你的行为准则**」;
- 或在仓库根建一个 `AGENTS.md`,内容写 `见 CLAUDE.md` 并把关键边界抄过去。

> 前者更省事且不会产生"一式两份"的分叉;后者更符合 Codex 的默认习惯。
> **选后者的话记住:两份文件从此要同步改** —— 这正是本项目对"刻意的重复"
> 一贯的处理方式:要么别重复,要么配一道检查。

### 4.4 其他 agent(workbuddy、zcode 等)

**本项目未在这些工具上实测过**,所以这里不给专属命令 ——
写错的命令会被原样粘贴,那比不写更坏。

按 **4.1 的通用做法**即可:提示词本身与 agent 无关,你只需要知道两件事:

1. 怎么在**指定目录**启动它;
2. 它读**哪个文件**当持久指令(`CLAUDE.md` / `AGENTS.md` / 其他)——
   若都不读,就在提示词开头加一句「先读 `CLAUDE.md` 并遵守其中的权责边界」。

## 5. 装完之后:配置

### 5.1 密钥与后端

密钥只在**环境变量**里,不落盘:

```bash
export GLM_API_KEY=...        # GLM(默认后端)
export DEEPSEEK_API_KEY=...   # DeepSeek
export KIMI_API_KEY=...       # Kimi
```

切后端不用手改 `config.yaml`:

```bash
bash scripts/sage-backend.sh            # 看当前后端 + 可用清单
bash scripts/sage-backend.sh deepseek   # 切到 DeepSeek
```

可用后端由仓库根实际存在的 `config.*.yaml` 决定 —— 自己加一个 profile 就会出现在清单里。

> **切换后 `config.yaml` 在 git 里显示为已修改是正常的**(活动配置就是那个文件)。
> 另外:**思维模式一律显式关掉**。概念抽取时思维链会吃掉 8K+ 字符撑爆 token 预算,
> 返回空结果 —— 别指望"默认应该是关的",文档往往不写默认值。

### 5.2 连通性

```bash
sage-wiki doctor
```

它会报出活动后端与连通性。**这一步过不了就别往下走** —— 后面每一步都依赖它。

### 5.3 MCP 接入

`.mcp.json` 用相对路径 `--project .`,换机器无需修改。
只有当你的客户端**不以 vault 为工作目录**启动 MCP server 时,才需要改成绝对路径。

## 6. 加入自己的知识库

### 6.1 先理解双库:为什么新克隆里没有 `_wiki/`

`raw/`、`_wiki/`、`material/`、`writing/`、`reports/` 是**个人内容**,
它们在**另一个私有内容库**里,经软链挂进代码库。
**新克隆里这些目录不存在,是设计如此,不是装坏了。**

```bash
bash scripts/init-vault.sh --dry-run   # 先看计划
bash scripts/init-vault.sh             # 建内容库 + 软链 + git init
bash scripts/vault.sh repo             # 验证:应打印你的内容库路径
```

> **这一步别跳过,也别只看它"没报错"。**
> `_wiki` 软链不存在时,`vault.sh` 会**静默退回单库模式** ——
> 之后 `vault.sh commit` 会把你的个人内容提交进**代码库**。
> 所以第三条命令是**验收**,不是装饰:它打印的必须是内容库路径。

### 6.2 存量资产放哪

| 你有的东西 | 放进 | 会不会被编译 |
|---|---|---|
| 网页剪藏、文章库 | `raw/clippings/` | **会**(声明在 `config.yaml` 的 `sources`) |
| 待深读的重要文章 | `raw/todo/` | 不会 —— 留给你和 agent 做对话式精读 |
| 本地 PDF | `raw/pdfs/` | **会** |
| 卡片笔记增量导出 | `raw/flomo/<日期>/` | 仅 `delta/` 子目录会 |
| 敏感冷存 | `raw/private/` | **永不入库** |

> **不是所有文字都该编译。** 评论性散文、随笔类语料会抽出大量"单篇一次性表述"
> 与修辞手法,把已收敛的概念体系淹掉。这类内容**只收藏、不编译** ——
> 放在不被 `sources` 声明的目录里即可。

### 6.3 加新来源

在 `config.yaml` 的 `sources` 里加一个目录就行。
两条语义要知道:

- `sources` 里显式声明的目录**优先于** `ignore`(所以 `raw/flomo` 整体被忽略、
  而 `raw/flomo/delta` 仍会编译);
- 加完**先小批量试编**一次再放全量 —— 编译按量计费,概念抽取的产出与语料类型强相关。

## 7. 编译机制怎么运行

### 7.1 一条命令,六步流水线

```bash
bash scripts/compile.sh
```

| 步 | 做什么 | 失败会怎样 |
|---|---|---|
| 1/6 | `sage-wiki compile` —— 抽概念、写摘要页 | 中止 |
| 2/6 | OKF 合规注入(`type` / `stale_after`) | 记账,继续 |
| 3/6 | 重建 `index.md` | **记账,继续**,但末尾非零退出 |
| 4/6 | `sage-wiki lint`(记账到 `reports/lint/`) | 同上 |
| 5/6 | 生成本地浏览站 `browse/wiki/`(含关系图) | best-effort;缺 `markdown` 包只告警跳过 |
| 6/6 | 提交编译产物(经 `vault.sh` 落到内容库) | — |

> **为什么第 3、4 步失败不中止**:中止会丢掉本轮编译产物(第 6 步才提交)。
> 但**末尾必须非零退出** —— 否则"跑完了但有两步挂了"会被读成成功,
> 这正是本项目反复强调的:**失败必须长得像失败**。

### 7.2 日常一律走 `compile.sh`,不要裸跑 `sage-wiki compile`

裸跑不维护 `index.md`、不触发 lint、不重建浏览站。
`compile.sh` 把这些串成一条命令,少一步都会让知识库慢慢"脱节"。

### 7.3 增量靠 manifest,不靠归档

引擎用 `.manifest.json` 里的 hash 判断哪些来源变过 —— **只编译变化的部分**。

所以:

- **不要"编译完就把剪藏归档走"**。文件消失会让引擎标记幻影 `removed`;
- **不要删或清空 `.manifest.json`**。清空 = 下次全量重编 = 全额 API 费用;
- 升级引擎前顺手 `cp .manifest.json ~/manifest.bak`,一秒的事。

### 7.4 定时编译

跑通之后可以挂定时任务。两个坑:

- **cron 不读你的 shell profile** —— `PATH` 里要显式带上 `$HOME/go/bin`,
  API Key 也要在 cron 能读到的地方;
- **系统 `python3` 可能是很旧的版本**。用仓库虚拟环境里的解释器,别写裸 `python3`。

## 8. 验收清单

装完逐条核对,**没通过的照实记下来**:

- [ ] `sage-wiki doctor` 通过,API 连接正常
- [ ] `bash scripts/vault.sh repo` 打印的是**内容库**路径(不是代码库)
- [ ] `bash scripts/compile.sh` 跑完**退出码为 0**(非零 = 有步骤挂了,见 7.1)
- [ ] `_wiki/` 下生成了摘要页与概念页,`index.md` 已更新
- [ ] `reports/lint/` 下有本次 lint 记账
- [ ] 本地浏览站 `browse/wiki/index.html` 能用 `file://` 打开
- [ ] Web Clipper 能把文章剪藏进 `raw/clippings/`
- [ ] `git status` 里**没有**你的个人内容(在内容库里才对)

## 9. 出问题时先看这几条

| 现象 | 多半是 |
|---|---|
| `no non-test Go files` | `go install` 的路径漏了 `/cmd/sage-wiki` |
| `command not found: sage-wiki` | `$HOME/go/bin` 不在 `PATH` |
| `doctor` 报连不上 | API Key 没 export,或 export 在另一个终端里 |
| 编译返回空结果 / `finish_reason=length` | 思维模式没关(见 5.1) |
| `vault.sh repo` 打印代码库路径 | 软链没建成,**先修这个再做任何提交** |
| 编译很久且账单意外 | `.manifest.json` 被清空过,触发了全量重编 |
| 浏览站没生成 | 缺 `markdown` 包(`pip install -r requirements.txt`),不影响编译 |
| agent 说"完成"却没有输出 | 让它重跑并贴真实输出 —— **没有输出就等于没做** |

## 相关

- [安装指南](install.md) —— 权威步骤(人手动执行)
- [使用手册](usage.md) —— 装完之后的每周节奏
- [系统如何运作](architecture.md) —— 架构、流水线与隐私边界
- [FAQ 与避坑](faq.md) —— 风险红线与脚本报错排查
