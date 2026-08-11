---
title: 一键安装(给 Agent)
---

# 一键安装:一段提示词装好

> 在**仓库根目录**启动你的编码 agent,把下面整段发给它。约 20 分钟。
> 想知道每步在做什么、装完怎么配、编译机制怎么转 → 看《[用 AI Agent 安装](agent-install.md)》。

## 装之前(30 秒)

- 已 `git clone` 本仓,并 `cd` 进去
- 机器上有 **Git**;**Go / Node.js / Python 3.9+** 缺哪个让 agent 告诉你怎么装
- 手上有一个大模型 **API Key**(GLM 默认 / DeepSeek / Kimi 任一)—— **先别填,它会在该填的时候停下来问你**

## 提示词(整段复制)

```text
你是我的安装助手。在当前目录把「第二大脑」装起来。

权威步骤是仓库里的 docs/guide/install.md —— 先完整读它,按它执行,以它为准。

铁律:
1. 密钥你不碰。需要 API Key 时停下来告诉我该 export 哪个变量,由我自己填;
   不要写进任何文件,不要回显任何密钥值。
2. 花钱的一步先问。`bash scripts/compile.sh` 会按量调用大模型 API,
   我明确说"可以编译"之前不要跑。
3. 已初始化的仓库里永远不要跑 `sage-wiki init`。
4. 不要替我 commit 或 push。
5. 每条命令都把真实输出贴出来再下结论。失败就停下报错,
   不要自己绕过去,不要用"应该没问题"结束一步。

分三段做,每段结束等我确认再继续:

A 只读盘点(这一段不许安装任何东西)
  报告 git / go / node / python3 的实际版本;`pwd` 与 `ls` 确认在仓库根
  (应能看到 config.yaml、CLAUDE.md、scripts/);`command -v sage-wiki`。

B 安装与配置
  按 install.md 装脚本依赖与 sage-wiki(主包在 cmd/ 下,路径漏了会报错);
  跑一遍 install.md §3.1 的行为验证确认引擎版本,不符就告诉我别继续;
  `bash scripts/init-vault.sh --dry-run` 把计划给我看,我同意后再真建;
  `bash scripts/vault.sh repo` 必须打印内容库路径 ——
  打印代码库路径就停下来告诉我(软链没建成);
  最后 `sage-wiki doctor`,输出原样贴给我。

C 首次编译(我同意才做)
  `bash scripts/compile.sh`;跑完按 install.md 的「首周验收清单」逐条核对,
  逐条说通过还是没通过,没通过的照实说。
```

## 它会停下来问你三次

| 时机 | 你要做什么 |
|---|---|
| A 段结束 | 看一眼环境盘点,确认没问题 |
| B 段中间 | **自己 export API Key** —— agent 不碰密钥 |
| C 段之前 | 批准首次编译 —— **这一步按量计费** |

除此之外它应当一路自己走完,并且**每条命令都贴真实输出**。
它说"完成"却没有输出时,让它重跑并贴出来 —— **没有输出就等于没做**。

## 装完

```bash
sage-wiki doctor                # 连通
bash scripts/vault.sh repo      # 必须是内容库路径
```

`git status` 里**不该**出现你的个人内容(它们在内容库里)。

出问题、想加自己的知识库、想搞清楚编译机制 →
《[用 AI Agent 安装](agent-install.md)》有完整的配置、接入与排障。
