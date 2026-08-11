# 第二大脑 · 个人知识库工具集

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![tests](https://img.shields.io/badge/tests-187%20passing-brightgreen.svg)](tests/)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)

一个由 LLM 持续编写与维护的、可复利的个人 Wiki 知识库。**Wiki 不是 RAG** —— 知识只编译一次,此后持续保鲜。

> 打个比方:**Obsidian 是 IDE,LLM 是程序员,Wiki 是代码库。**

每加入一个新来源,LLM 不是索引它,而是读它、提炼它、整合进已有 Wiki——更新实体页、修订摘要、标注矛盾。知识库因此是一个持续复利的制品,而不是每次提问都从零拼图的检索管道。

先看清整套系统怎么运作:[系统如何运作](docs/guide/architecture.md)——三层架构 / 双库布局 / 编译流水线 / 四道防腐门禁 / 隐私边界,一页看完。

完整设计见 [PRD](docs/prd/第二大脑-个人知识库-PRD.md);上手见[安装指南](docs/guide/install.md)与[使用手册](docs/guide/usage.md)。

## Workbuddy 一键安装

本公开仓已经包含飞书授权与同步安装器，不需要私有仓邀请。
完整操作见 [Workbuddy 专用指南](docs/guide/workbuddy.md)。

```bash
# macOS / Linux
./install-second-brain
```

```powershell
# Windows 原生 PowerShell（不需要 WSL）
powershell -ExecutionPolicy Bypass -File .\install-second-brain.ps1
```

安装器只监听 `127.0.0.1`。App Secret 通过标准输入交给 lark-cli，token 由 lark-cli
保存在本机安全存储；凭证和飞书内容不会进入本仓。

## 双库设计:代码与内容分离

**本仓只含代码/工具/文档,不含任何个人内容。** 你的知识内容放在**你自己的另一个私有仓**里,经符号链接挂进工作目录:

```
second-brain/
├── mind-kit/      ← 本仓(代码)
└── my-vault/      ← 你的私有内容库(自建)
```

所以**克隆后不会有 `_wiki/`、`material/`、`raw/` 这些目录**——这是设计如此。一条命令建好自己的:

```bash
bash scripts/init-vault.sh --dry-run   # 先看计划
bash scripts/init-vault.sh             # 建内容库 + 软链 + git init
bash scripts/vault.sh repo             # 验证:应打印你的内容库路径
```

Windows 用户由 `install-second-brain.ps1` 自动调用跨平台初始化器并使用目录 Junction，
不要求管理员权限或 Developer Mode。

## 快速开始

```bash
# 1. 依赖
pip install -r requirements.txt
pip install -r requirements-dev.txt      # 参与开发时
bash scripts/install-hooks.sh            # pre-push 自动跑 pytest

# 2. 建自己的内容库(见上)
bash scripts/init-vault.sh

# 3. 配后端 API Key(别写进任何文件)
export GLM_API_KEY=...                   # 默认 GLM;或 KIMI_API_KEY 切 Kimi
bash scripts/sage-backend.sh kimi        # 切后端(可选)
sage-wiki doctor                         # 诊断连接

# 4. 首次编译
cp 你的文章.md ../my-vault/raw/clippings/
bash scripts/compile.sh                  # 编译 → 索引 → lint → 保鲜 → 浏览站 → 提交
```

Windows 原生 PowerShell 对应命令：

```powershell
.\compile-second-brain.ps1 -DryRun       # 先估算，不写入
.\compile-second-brain.ps1               # 确认后正式编译
```

**外部依赖**:编译引擎 [sage-wiki](https://github.com/xoai/sage-wiki)(Go 实现,MIT,本仓不含)需自行安装并置于 `PATH`;
`pandoc` 用于生成文档站(可选)。

> 未安装 sage-wiki 时,**本地检索、写集校验、决策队列、保鲜复核、报表**等能力仍可用,仅**编译链路**不可用。

在 Linux 服务器上从零部署,见[服务器部署指南](docs/guide/setup-linux-server.md)。
贡献者的 Windows 原生测试由 GitLab CI/CD 执行，见
[GitLab Windows Runner 配置](docs/guide/gitlab-windows-ci.md)；不要为此新增 GitHub
Actions `windows-latest` job。

## 目录结构

```
mind-kit/
├── config.yaml             # 编译引擎活动配置(默认 GLM 后端)
├── config.glm.yaml         # GLM profile(glm-4.5-flash)
├── config.kimi.yaml        # Kimi profile(kimi-for-coding)
├── CLAUDE.md               # Schema:各角色权责边界与工作流(系统"宪法")
├── prompts/                # 提示模板(概念/摘要/文章/捕获/配图)
├── scripts/                # 自动化(见下)
├── tests/                  # pytest(脚本改动强制测试先行)
├── evaluation/             # 检索与质量回归基线(合成语料)
├── docs/{prd,guide}/       # 设计文档与指南(.md 为权威版本)
├── site/                   # 文档站静态页(build-site.sh 生成)
│
│   ── 以下为软链,真实内容在你的私有内容库 ──
├── raw/                    # {clippings,todo,archive,pdfs,assets}/ 原始来源,只读
├── _wiki/                  # {summaries,concepts,entities}/ 编译产出 + outputs/ 查询产出
├── material/               # {quotes,stories,references,cases,frameworks,data}/ 六类素材
├── writing/                # 写作成稿
└── reports/                # {daily,weekly,lint}/ 工作日志与健检记账
```

## scripts/ 核心

| 脚本 | 作用 |
|---|---|
| `init-vault.sh` | 建内容库骨架 + 双库软链(**新用户从这开始**) |
| `vault_init.py` | macOS / Linux / Windows 共用的非覆盖式 Vault 初始化核心 |
| `compile.sh` | 编译全流水线:编译 → 索引 → lint → 保鲜 → 决策校验 → 提交 |
| `compile_second_brain.py` | Windows PowerShell 使用的跨平台编译流水线 |
| `update-all.sh` | 一键全量更新(日报 → 编译 → 门户 → 文档站);支持网页按钮与定时 |
| `vault.sh` | 内容库提交/推送(**个人内容唯一提交漏斗**,带写集校验门禁) |
| `searchlib.py` | 本地检索:BM25 + CJK bigram + RRF 多通道 + 同义扩展 |
| `brain-server.py` | 本地服务:静态门户 + `/api/search` + `/api/query` |
| `decision.py` | 待确认决策队列(状态机,审批与执行分离) |
| `freshness.py` | 半衰期保鲜复核(只提示不自动改) |
| `validate_write_set.py` | 写集校验(提交前拦住 frontmatter 损坏等) |
| `daily-report.py` / `weekly-report.py` | 日报 / 周报自动盘点 |

## 让它规模化不腐化的四道机器

知识库越大越怕漂移与静默腐化。除理念外,系统落了四道**确定性可执行**的机制——不是提示词里的软约束,而是脚本、测试与门禁:

1. **本地检索栈** —— BM25 + 中文 bigram 分词 + RRF 多通道融合 + 双语同义扩展,秒级、不走 LLM,索引按输入指纹自动刷新
2. **评测与回归** —— 检索 golden case(MRR/Top-1)与质量 required/forbidden token 断言锁住认知边界;基线只增不减
3. **决策队列 + 保鲜** —— 须先确认的动作走状态机(审批与执行分离);重要页按半衰期到点提示复核
4. **写集校验门禁** —— 提交前对变更页跑确定性校验,坏页拦在入库前

开发纪律遵循 [Superpowers](https://github.com/obra/superpowers):测试先行 · 系统化优于拍脑袋 · 简单为第一目标 · 用证据而非声称。**脚本改动强制先写会失败的测试**,push 前钩子跑全量 pytest(细则见 `tests/README.md`)。

## 红线

- `_wiki/summaries|concepts|entities` 是编译引擎的领地,LLM 只读;产出写到 `_wiki/outputs/`
- 原始来源只读不写;笔记类原始导出永不修改,只编译其增量目录
- 处理完的 `todo` 移入 `archive/`,不要移回 `clippings/`(会重复编译)
- 先有写作/决策任务,再让 AI 从积累里挖宝 —— 不为整理而整理

## 许可

[MIT](LICENSE)。本仓不含任何个人知识内容;你的内容属于你自己的私有库。
