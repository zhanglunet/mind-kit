# 更新日志

本文件记录本代码库(脚本、配置、文档)的重要变更。知识内容的时序记录在你自己内容库的 `_wiki/log.md`。

## v1.4 — 2026-08-03

**纯文档发布,无代码行为变化。** 两页各补一张全景信息图,
顺带把一条不太好看的查证结论摆到明面上。

### 新增:两张「四层一图」

**《系统如何运作》** —— 按**数据流**画(与该页第 1 节的权责视图互补,不重复):

| 层 | 内容 |
|---|---|
| 来源层 | `raw/*`,只读,唯一真相 |
| 加工层 | **两条路**:① `sage-wiki compile` 引擎批量 ② LLM 对话式 ingest 人在环 |
| 知识层 | 引擎领地(LLM 只读)与 LLM 领地,各自的门禁标在写入点上 |
| 调用层 | 索引 / 浏览站 / 本地检索 / 引擎查询,**含一条回流箭头** |

图里说清了三件文字不容易讲明白的事:加工是**两条路而非一条**(只有 `raw/todo`
走人工深度处理,`clippings`、`flomo/delta`、`pdfs` 三者都在 `config.yaml` 的
`sources` 里由引擎自动编译);门禁挂在**写入点**上而不是挂在嘴上;调用层那条
**回流**才是"知识复利"的实现——没有它,这就只是个搜索引擎。

**《OKF 合规》** —— 按**流水线环节**画:来源层 → 引擎层 → 合规层
(① `okf.py --fix` → ② `build-index.py` → ③ `okf.py --check`,标注顺序约束与自愈回环)
→ 消费层(各字段分别被谁读取)。

两张图共用同一套视觉语汇(单张内联 SVG、左侧层轨、CSS class 上色而非写死 `fill`),
并排看时不用重新学一套符号;浅/深主题自动跟随,窄屏时图容器自身横向滚动、不压缩图形。

### 一条如实的查证结论:`type` 目前没有消费者

v1.3 补齐了 OKF 要求的 `type` 字段。事后把整个代码库翻了一遍,结果是:

```
读 entity_type 的：build-index.py:71   build-wiki-site.py:107
读 「类别」 的：   build-wiki-site.py:230
读 frontmatter type 的：  只有 okf.py 自己
```

`indexlib` / `searchlib` 一次没碰。也就是说,**这个字段今天的实际产出是零** ——
真正划算的是顺带做成的 `okf.py --check`(编译引擎领地此前零校验)与
`stale_after` 链路,而那两件都不需要 OKF。留着 `type` 的理由只有一条:
成本≈0 的互操作期权,等 OKF 生态工具出现时才兑现。

这条结论已画进信息图的末层(四条实线通向真实消费者,`type` 一条虚线指向空框),
不是藏在正文里。**若你 fork 了本项目,可据此自行决定要不要保留这一步。**

### 门禁

文档站的「两份载体」检查改成完全表驱动:章节数与主题词都写在 `PAIRS` 表里,
加新页或改章节结构会被门禁挡下,不会出现"改了一边忘另一边"。

## v1.3 — 2026-08-03

对齐 Open Knowledge Format;修掉一批「失败伪装成成功」的缺陷——
它们的共同点是出错时**看起来仍然是绿的**,所以比崩溃更危险。

### 新增:OKF 合规(Open Knowledge Format v0.2)

[OKF](https://github.com/GoogleCloudPlatform/knowledge-catalog/tree/main/okf) 是
「用 markdown + YAML frontmatter 表示知识」的中立格式。本项目的形态与它高度重合
(bundle=目录、保留 `index.md`/`log.md`、容忍未知键),**硬性要求只有两条**:
每页有合法 frontmatter、`type` 非空。

- 新增 `scripts/okf.py`:`--check` 只读体检(不合规非零退出)/ `--fix` 幂等注入
- `type` 由目录 + 已有键**确定性**推出,不用 LLM:概念页直接取 `entity_type`
  (值域 concept / technique / claim 如实传导,不是一律拍成 concept)
- **只加不改**:已有 `type` 的页一字节不碰;`entity_type`、`类别`、`decision_type`
  等原有键一律保留——它们各有现成消费者,改名等于为合规砸自家管线
- `compile.sh` 从五步变六步:`--fix` 在重建 index **之前**(索引读 frontmatter 生成,
  注入晚了就读到上一轮旧字段),`--check` 进 lint 记账;顺序由测试钉死
- **补上引擎领地的门禁**:`validate_write_set.py` 的作用面不含
  `_wiki/{summaries,concepts,entities}`,此前那三个目录零校验
- `stale_after`:把既有的半衰期保鲜(`volatility` / `half_life_days` + `last_confirmed`)
  映射成 OKF 键,由 `--fix` 自动算出

文档:`docs/guide/okf.md`(文字版)+ 文档站「OKF 合规」图解页,含对比表与流水线图示。

### 别假设 `python3` 就是对的解释器

真机上 43 个测试同时变红,同一个根因:系统 `python3` 可能是 EOL 的 3.6,
而依赖装在 `.venv` 里。

- 新增 `scripts/_pyresolve.sh`:解析顺序 `<repo>/.venv/bin/python` → `$MIND_PYTHON`
  → `python3`(版本够才用)→ 扫 `python3.13…3.9` → 大声告警后回落
- 所有 `scripts/*.sh` 统一走它;新增门禁 `tests/test_interpreter_hygiene.py`,
  裸调 `python3` 会被拦下

### 修复:失败必须长得像失败

| 位置 | 出错时会发生什么 | 此前看起来像 |
|---|---|---|
| `vault.sh` 提交 | git 没有身份配置、钩子拒绝……提交失败 | **「无改动可提交」** |
| `update-all.sh` 互斥锁 | 系统没有 `flock(1)`(macOS 就没有) | 继续跑,像是拿到了锁 |
| 隐私门禁 | `git ls-files` 出错返回空清单 | 扫过了,零命中 |
| 隐私门禁 | 非 ASCII 文件名被 quotepath 转义、读不到 | 中文名文件是干净的 |
| 发布门禁 | 公开版树只 `git init` 没 `git add` | 扫了 0 个文件却报通过 |

`vault.sh` 那条最要命:`git commit` 对「没东西可提交」和「提交出错」返回**同一个非零码**,
老写法 `commit || echo "无改动可提交"` 把两者混为一谈——表现是编译流水线报成功,
而产物根本没入库。现在先用 `git diff --cached --quiet` 判断暂存区空不空,再决定这次非零是哪一种。

### 其他

- `update-all.sh`:内容库的拉取/推送做进编排(此前只写在文档里,靠人记得手动跑);
  跨进程锁改成可移植实现(无 `flock` 时用 `mkdir` + PID 存活检查,而不是跳过互斥)
- 新增 **DeepSeek** 编译后端(`config.deepseek.yaml`);`sage-backend.sh` 改为
  从磁盘上实际存在的 `config.*.yaml` 发现后端,不再三处维护硬编码清单
- 文档站的「两份载体」门禁改成表驱动:每个手工页都自动检查
  文字版/可视化版都在、主题一致、章节数一致、**首页与模板导航可达**
  (手工页不过 pandoc,漏挂导航就是个只有知道 URL 才进得去的孤儿页)

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
