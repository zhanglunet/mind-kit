# 更新日志

本文件记录本代码库(脚本、配置、文档)的重要变更。知识内容的时序记录在你自己内容库的 `_wiki/log.md`。

## v1.2 — 2026-07-25

新增一页「系统如何运作」总览;发布门禁堵掉一个真实存在的盲区。

### 新增:《系统如何运作》

一页看完整套系统:三层架构 / 双库布局 / 七步编译流水线 / 四道防腐门禁 /
查询两条路 / 隐私边界 / 开发纪律。

- 文字版 `docs/guide/architecture.md`(GitHub 上可直接读)
- 可视化版:文档站的「系统运作」页,首页与各生成页导航均已接入

### 发布门禁加固(重要)

此前的禁忌词门禁是纯文本 `grep`,对 **PDF / Office 这类压缩容器一律盲视**——
规则写得再全,也读不到它们的正文。修法不是继续加规则,而是**整类拒收**:

- 发布时新增「不可扫描格式门禁」:公开版树里出现 `pdf/docx/xlsx/…` 即中止发布
- 相应地,`docs/prd/` 下的二进制导出件(PDF / DOCX)与一份 HTML 导出不再随公开版发布,
  **权威版本一律是同目录的 Markdown**,内容不受影响
- 移除 `scripts/convert-sina-blog.py`:它读的 `raw/articles/` 在任何公开克隆里都不存在,
  本就是死代码

### 文档修正

- 服务器部署指南的目录命名此前自相矛盾(第 1 步克隆成 `mind`,第 9 步却 `cd mind-kit`)。
  统一为 **`mind-kit/`(代码)+ `mind-vault/`(内容)**——后者是 `init-vault.sh` 的默认值。
  已按旧指南装好的人不必改动,只需知道文档里的路径示例现在用 `mind-kit`。
- 文档站互链改写不再依赖硬编码白名单,新增页面不会再漏改成死链

## v1.1 — 2026-07-25

面向使用者的更新体验修复,以及 Linux 兼容性改进。

### 修复:可以正常 `git pull` 更新了(重要)

此前每次发布都会**重写仓库历史**,导致已克隆的使用者更新时直接失败:

```
git pull            → fatal: refusing to merge unrelated histories
git pull --ff-only  → fatal: Not possible to fast-forward, aborting
```

现在发布采用**线性追加**——新版本接在上一版之后,使用者直接 `git pull` 即可快进更新:

```bash
cd mind-kit && git pull
```

想让服务器自动跟进上游更新,加一条 cron:

```cron
0 8 * * * cd $HOME/second-brain/mind-kit && git pull -q
```

> `git pull` 只更新工具代码,**不碰你的内容库**——你的知识内容在自己的私有仓里。

### Linux 兼容性

- `update-all.sh` 的 PATH 补上 `/usr/local/bin` 与 `~/.local/bin`,Linux 上对 `sage-wiki` / `pandoc` 的探测更可靠(此前只找 Homebrew 路径)
- 服务器部署指南新增「更新代码」一节,含自动跟进 cron 与更新后自检

## v1.0 — 2026-07-25(首个公开版)

第二大脑工具集的首个公开发布。核心能力:

### 编译与内容管线
- **双库布局**:代码库(本仓)与私有内容库分离,内容目录经软链挂入;`scripts/init-vault.sh` 一键建内容库骨架 + 软链
- **编译流水线** `compile.sh`:编译 → 重建索引 → lint 记账 → 保鲜复核 → 决策队列校验 → 生成本地浏览站 → 经 `vault.sh` 提交
- **一键全量更新** `update-all.sh`:日报 → 编译 → 订阅台账 → 门户 → 文档站;缺工具自动跳过,支持网页按钮触发与定时自启
- 后端可切换:GLM(默认)/ Kimi,OpenAI 兼容端点,`sage-backend.sh` 一键切换

### 规模化不腐化的四道机器
- **本地检索栈** `searchlib.py`:BM25 + CJK bigram 分词 + RRF 三通道融合 + 双语同义扩展;`/api/search` 秒级返回,不走 LLM,索引按输入指纹自动刷新
- **评测与回归** `evaluation/`:检索 golden case(MRR / Top-1)+ 质量 required/forbidden token 断言;三后端(fixture / local / brain),基线只增不减
- **决策队列** `decision.py`:须先确认的动作走状态机(new → approve/reject/defer → apply,审批与执行分离),Dataview 单一看板入口
- **保鲜复核** `freshness.py`:半衰期模型(volatility high/medium/low = 30/90/365 天),到点提示复核,只提示不自动改
- **写集校验** `validate_write_set.py`:提交前对变更页跑确定性校验(frontmatter 闭合与键值形态、含冒号值引号化、保鲜字段、决策不变量),坏页拦在入库前

### 服务与界面
- **本地服务** `brain-server.py`:静态托管门户 + `POST /api/search`(本地检索)+ `POST /api/query`(引擎查询,带中文分词兜底与同义扩展)+ `/api/update-all`(网页一键全量更新,本地 Origin 护栏、后台单飞)
- **门户与站点**:`build-portal.py` 个人入口、`build-wiki-site.py` 本地浏览站(含关系图)、`build-site.sh` 公开文档站
- **工作日志**:`daily-report.py` / `weekly-report.py` 从 git 提交与 log 自动盘点,保留手写区

### 开发纪律
- 遵循 [Superpowers](https://github.com/obra/superpowers) 四原则:测试先行 / 系统化 / 简单 / 用证据
- **脚本改动强制 pytest-first**(RED → GREEN → REFACTOR);pre-push 钩子跑全量 pytest;GitHub Actions 服务端兜底
- 可执行门禁:个人标识形状检查、决策状态机不变量、写集校验 —— 规范由脚本执行,而非只写在文档里
