---
title: 安装指南
---

# 安装指南

> 目标:30 分钟内把"第二大脑"骨架在你的机器上跑起来。完整设计依据见《第二大脑-个人知识库-PRD》§10.1 与附录 B–D。

## 0. 前置要求

| 依赖 | 用途 | 检查命令 |
|---|---|---|
| Git | 版本化与归档判据(必装) | `git --version` |
| Go 运行环境 | 安装 [sage-wiki](https://github.com/xoai/sage-wiki) 编译引擎 | `go version` |
| Node.js | 安装 Claude Code CLI | `node --version` |
| Python 3.9+ | 运行仓库脚本(索引 / 本地浏览站 / 报表等) | `python3 --version` |
| Obsidian | 存储/写作界面(桌面端) | — |

## 1. 获取 Vault 骨架

```bash
git clone <你的仓库地址> mind
cd mind
```

骨架自带根目录三件套:`config.yaml`(编译引擎配置)、`.mcp.json`(MCP 接入)、`CLAUDE.md`(权责边界"宪法")。

> **拆库后注意**:`raw/`、`_wiki/`、`material/`、`writing/`、`reports/{daily,weekly,lint}` 是**个人内容**,在**另一个私有内容库**里,经软链挂进来(见 README「双库设计」)。所以新克隆里**这些目录并不存在**,这是设计如此。
> 一条命令建好自己的内容库并接上软链:
>
> ```bash
> bash scripts/init-vault.sh --dry-run   # 先看计划
> bash scripts/init-vault.sh             # 建内容库 + 软链 + git init
> bash scripts/vault.sh repo             # 验证:应打印你的内容库路径
> ```
>
> **别跳过**:`_wiki` 软链不存在时 `vault.sh` 会静默退回单库模式,之后 `vault.sh commit` 会把内容提交进**代码库**。
> 在 Linux 服务器上从零部署,见[在 Linux 服务器上安装与使用](setup-linux-server.md)。

若从零开始而非克隆:先 `git init && git add -A && git commit -m "init"`。**git 必须在首次编译前就绪**——归档脚本依赖 git 记录判断哪些剪藏已编译。

### 1.1 安装脚本依赖

```bash
pip install -r requirements.txt
```

`scripts/` 下绝大多数脚本只用 Python 标准库,**唯一的第三方依赖是 `markdown`**(供 `scripts/build-wiki-site.py` 生成本地浏览站)。不装也不影响编译:`compile.sh` 第 4 步(生成浏览站)是 best-effort,缺 `markdown` 时只告警跳过、不中断编译与提交。

## 2. 设置 API Key(GLM / DeepSeek / Kimi)

编译引擎 `sage-wiki` 接的是 **OpenAI 兼容**的国产端点,默认 **GLM**,可一键切换。密钥写进 shell profile(如 `~/.zshrc`),**不要落进任何仓库文件**:

```bash
export GLM_API_KEY=...        # GLM(默认后端)
export DEEPSEEK_API_KEY=...   # DeepSeek
export KIMI_API_KEY=...       # Kimi
```

各 profile 已内置端点与模型,无需手填:

| 后端 | env 变量 | 端点(OpenAI 兼容) | 模型 | 配置文件 |
|---|---|---|---|---|
| **GLM**(默认) | `GLM_API_KEY` | `open.bigmodel.cn/api/coding/paas/v4` | `glm-4.5-flash` | `config.glm.yaml` |
| **DeepSeek** | `DEEPSEEK_API_KEY` | `api.deepseek.com/v1` | `deepseek-v4-flash` / `-pro` | `config.deepseek.yaml` |
| **Kimi** | `KIMI_API_KEY` | `api.kimi.com/coding/v1` | `kimi-for-coding` | `config.kimi.yaml` |

**切换后端**(sage-wiki dev build 的 `--config` 未接线,只能替换活动 `config.yaml`):

```bash
bash scripts/sage-backend.sh            # 看当前后端 + 可用清单
bash scripts/sage-backend.sh deepseek   # 切到 DeepSeek
bash scripts/sage-backend.sh glm        # 切回 GLM
```

可用后端由仓库根实际存在的 `config.*.yaml` 决定——自己加一个 profile 就自动出现在清单里,不必改脚本。

> **切换会让 `config.yaml` 在 git 里显示为已修改**,这是正常的(活动配置就是那个文件);
> `git checkout config.yaml` 可还原成仓库默认的 GLM。

> **思维模式一律显式关掉**(profile 里的 `extra_params.thinking.type: disabled`)。
> GLM 与 DeepSeek v4 都支持"思考",而概念抽取时思维链会吃掉 8K+ 字符撑爆 token 预算,
> 返回 `finish_reason=length` 的空结果。别指望"默认应该是关的"——文档往往不写默认值。

`.gitignore` 已排除 `.env`、`*.key` 等常见密钥文件,但最稳妥的方式是密钥根本不落盘(只在环境变量)。

## 3. 安装四件套

1. **sage-wiki**(编译引擎):[https://github.com/xoai/sage-wiki](https://github.com/xoai/sage-wiki)(Go 实现,MIT)。
   主包在 `cmd/` 下,**装的时候别漏**(漏了会报 `no non-test Go files`):
   ```bash
   go install github.com/xoai/sage-wiki/cmd/sage-wiki@latest
   export PATH="$HOME/go/bin:$PATH"   # 写进 ~/.bashrc;cron 的 PATH 也要带上
   ```
   提供 CLI / MCP server / watch 监听。装完确保 `command -v sage-wiki` 有输出。
2. **Claude Code CLI**:`npm install -g @anthropic-ai/claude-code`,之后在 vault 根目录运行 `claude` 即可。
3. **Obsidian**:把本仓库目录作为 Vault 打开。
4. **Claudian 插件**(主交互界面):建议通过 BRAT 插件安装以获得自动更新;它在 Obsidian 侧栏内嵌 Claude Code,复用同一份 `CLAUDE.md` 与 `.mcp.json`。

再装四个 Obsidian 插件:**Web Clipper**(剪藏落地到 `raw/clippings/`)、**Templater**、**Dataview**(五维标签检索)、**BRAT**;附件目录设为 `raw/assets/`。

## 4. 校验配置与连接

```bash
sage-wiki doctor        # 验证 API 连接与配置
```

`config.yaml` 骨架已配置好来源目录、忽略清单与模型(当前单一 `glm-4.5-flash`,不分层),`doctor` 会报出活动后端与连通性。通常无需修改;两个关键语义请知悉:

- `sources` 声明 `raw/clippings`、`raw/flomo/delta`、`raw/pdfs` 三个来源;
- `ignore` 中的 `raw/flomo` 只排除原始导出,**delta/ 子目录因在 sources 中显式声明而优先生效**(引擎须满足 PRD §4.4 硬标准 5;首次编译后请按第 6 步验证)。

`.mcp.json` 使用相对路径 `--project .`,换机器无需修改;若你的客户端不以 vault 为工作目录启动 MCP server,再改为绝对路径。

## 5. 放入存量资产

- 文章库/剪藏 → `raw/clippings/`
- 待精读的重要文章 → `raw/todo/`
- 本地 PDF → `raw/pdfs/`
- 卡片笔记增量导出 → `raw/flomo/<日期>/`(可选,原样保留;flomo 管线保留但当前未启用)

## 6. 首次编译与验证

```bash
bash scripts/compile.sh        # 全流水线:编译 → 重建 index → lint → 生成本地浏览站 → 提交
```

> 日常编译一律走 `bash scripts/compile.sh`(而非裸 `sage-wiki compile`):dev build 不自动维护 `index.md`、不触发 auto_lint、浏览站也需重生成,`compile.sh` 把这些串成一条命令。**不做 auto-archive** —— sage-wiki 靠 manifest hash 增量,归档已编译剪藏反而让引擎标记幻影 "removed"。本地浏览站生成在 `browse/wiki/index.html`,`file://` 直接打开(含关系图,gitignore 不入库、不上公开站)。

**✅ 首周验收清单**

- [ ] `sage-wiki doctor` 通过,API 连接正常
- [ ] `bash scripts/compile.sh` 成功:`_wiki/` 生成摘要/概念页,`index.md` 更新,lint 记账到 `reports/lint/`
- [ ] 本地浏览站 `browse/wiki/index.html` 能 `file://` 打开(概念/摘要/产出/素材 + 关系图)
- [ ] Web Clipper 能把文章剪藏进 `raw/clippings/`
- [ ] Claudian 侧栏能调用编译引擎(MCP 连通)
- [ ] 编译后自动 commit 生效

下一步请阅读[使用手册](usage.md),建立每周节奏;想先搞清楚"这套东西整体怎么转"的,看[系统如何运作](architecture.md)。
