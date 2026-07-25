---
title: 使用手册
---

# 使用手册

> 一句话心法:**先有写作/决策任务,再让 AI 从积累里挖宝——知识库不是用来整理的,是用来调用的。** 北极星指标是"调用率":每周实际从库里调用素材或答案的次数(目标 ≥ 5 次/周)。

## 目录与权责速查

| 目录 | 谁写 | 说明 |
|---|---|---|
| `raw/**` | 人放入 | 原始来源,只读不改,唯一真相 |
| `_wiki/summaries·concepts·entities` | sage-wiki 全权 | LLM 只读;编译产物 |
| `_wiki/outputs/` | LLM 可写 | 查询产出与深度摄入摘要 |
| `_wiki/index.md`、`log.md` | 共同维护 | 只追加,不删除 |
| `material/**` | LLM 全权 | 六类写作素材 |
| `writing/**` | LLM 可写,人主导 | 写作成稿存档 |

日志格式统一为 `## [日期] 类型 ｜ 标题`(全角"｜")。

## 五大核心工作流

### 1. 自动摄入(剪藏)

浏览器 Web Clipper 剪藏 → 自动落地 `raw/clippings/` → sage-wiki watch 自动编译 → 编译后运行 `bash scripts/auto-archive.sh` 把已编译文件移入 `raw/archive/`。

归档判据以 git 快照为准:只有"已提交且编译后无改动"的文件才会归档,失败方向永远是"多留一周",绝不误归档。

### 2. 深度摄入(todo)

对标记进 `raw/todo/` 的重要文章,在 Claudian 侧栏执行五步:

1. 读文章,与你讨论关键要点(不跳过)
2. 在 `_wiki/outputs/` 写简要摘要页(不写 `summaries/`,那是编译引擎的领地)
3. 按六类框架抽素材存入 `material/`
4. 在 `log.md` 追加 `## [日期] ingest ｜ 标题`
5. 处理完把原文移入 `raw/archive/`——**不要移回 `clippings/`**(会被再次编译产生重复条目)

### 3. flomo 增量

```bash
# 把最新全量导出放入 raw/flomo/<日期>/ 后:
python3 scripts/flomo-delta.py raw/flomo/<日期>
sage-wiki compile
```

脚本比对指纹只输出**新增**笔记到 `raw/flomo/delta/delta-<日期-时分秒>.md`,原始导出永不修改。之后在侧栏用六类提取 prompt 处理 delta(偏好:重点①金句②复盘⑤框架,弱化③外部引用⑥数据)。

### 4. Query(查询)

1. 先读 `_wiki/index.md` 定位相关页
2. 深入相关页,综合答案,附 Wiki 内链接
3. **有价值的分析存入 `_wiki/outputs/`** 并记日志——让探索也复利,别让洞见死在聊天记录里

产品/竞品/融资/招聘决策用五维框架检索:市场与竞争 / 技术判断 / 产品与用户 / 人与组织 / 框架与心智模型。

### 5. Lint(健检)

定期让系统检查:页面间矛盾、被新来源推翻的旧声明、孤立页面、缺失交叉引用、值得新建的概念页、可联网补充的数据缺口。安全项(如补链接)可自动修复,变更进 git。

## 写作闭环

| 阶段 | 操作 | 产出 |
|---|---|---|
| 写作前 | 六类框架 prompt 全库提取素材 | `material/[主题]-素材库.md` |
| 写作中 | 取用金句/案例/数据,需深挖时即时 Query | 成稿草稿 |
| 写作后 | 新金句/判断回写 `material/`;分析存 `_wiki/outputs/`;成稿存 `writing/` | 库复利 + 存档 |

## 工作日志:日报与周报

持续记录在知识库上做过的工作,并方便合成周报。报告存在 `reports/`(不参与编译)。

**日报**——盘点前一天的工作:

```bash
python3 scripts/daily-report.py           # 默认盘点“昨天”
python3 scripts/daily-report.py --today    # 今天(截至此刻)
python3 scripts/daily-report.py --days 7    # 回填最近 7 天
```

脚本从三处**自动盘点**并生成 `reports/daily/YYYY-MM-DD.md`:git 提交(作者日期)、`_wiki/log.md` 条目、当天 flomo 增量——每条结论都挂 git sha 或 log 条目,可回溯。

每份日报底部有一个**"手记"区**(`<!-- 手记开始 -->…<!-- 手记结束 -->` 标记之间):在这里补写今日反思、决策复盘、库外工作,或让 LLM 填写。**重新生成日报时手记区原样保留**,只有上方的自动盘点部分会刷新。

**周报**——把一周日报聚合:

```bash
python3 scripts/weekly-report.py           # 上一个完整周(周一–周日)
python3 scripts/weekly-report.py --this-week
python3 scripts/weekly-report.py --last 7
```

生成 `reports/weekly/YYYY-Www.md`:汇总数字直接盘点本周期的 git 提交 + `log.md`(即使没生成过日报也准确),再加每日要点(缺日报的日子会标注)、分类小结、各日手记汇编,以及一个**"周度综述"区**留给 LLM 写叙事——在 Claudian 里让它读本周日报,写主线/进展/问题/下步。

**cron 化(可选)**:把日报生成挂到本机 cron,每天自动留档并提交。`date +%F`(今天,POSIX 可移植)作提交信息;`|| true` 只为吞掉"无改动可提交"这一非错误情形:

```cron
0 6 * * *  cd /path/to/mind && python3 scripts/daily-report.py && git add reports/daily reports/weekly && git commit -q -m "自动日报($(date +\%F) 生成)" || true
```

> macOS 自带 BSD `date` 语义不同,但这里只用了可移植的 `date +%F`,无需改动。

## 一键全量更新

把散落的更新命令收成**一条编排脚本** `scripts/update-all.sh`:按序跑 日报 → `compile.sh`(编译 + 索引 + lint + 保鲜 + 决策 + 浏览站 + 提交)→ 订阅台账页 → 门户入口页 → 对外文档站。逐步 best-effort:缺 `sage-wiki`/`pandoc` 的步骤自动跳过,真跑失败才记 ✗ 并非零退出。

```bash
bash scripts/update-all.sh --dry-run   # 先看计划(不执行、不落盘)
bash scripts/update-all.sh             # 全量更新
bash scripts/update-all.sh --pull      # 顺带先 git pull --ff-only 拉最新代码
```

**网页一键启动**:门户入口页(`browse/index.html`)的 hero 区有「🔄 全量更新」按钮——本地服务(`python3 scripts/brain-server.py`)在线时点亮,点击即在后台跑 `update-all.sh`,页面实时回显日志尾,完成显示 ✅/⚠️。按钮走 `POST /api/update-all` + 轮询 `GET /api/update-status`,只接受本地来源(挡跨站触发)。

**每天自动启动**(macOS LaunchAgent,每日 09:30):

```bash
cp scripts/com.mind.update-all.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.mind.update-all.plist
launchctl start com.mind.update-all      # 立即试跑一次;日志见 ~/.mind-update-all.log
```

> 按钮、定时、命令行三条路都调**同一个** `update-all.sh`(单一真相)。Linux/无 launchd 可改用 cron:`30 9 * * * cd /path/to/mind && bash scripts/update-all.sh`(睡眠漏跑问题同报告 cron)。

## 每周 / 每月节奏

**每周**

- **周一**:检查 `raw/clippings/` 积压 → `sage-wiki compile` → `bash scripts/auto-archive.sh`
- **周三**:逐篇深度摄入上周的 `todo` 文章 → 移入 `archive/`
- **周五**:新 flomo 导出 → 增量脚本 + 六类提取 → `sage-wiki lint`
- **周日/周一**:`python3 scripts/weekly-report.py` 合成上周周报,在综述区补一段小结
- 亦可开启 `compile --watch` 让 clippings 全自动化

**每日**

- `python3 scripts/daily-report.py` 盘点前一天工作(或交给 cron);随手在手记区补两句

**每月**

- 深度健检一次(`lint --fix` 处理安全项)
- 用 Obsidian 图谱观察连接质量成长
- 复评 `config.yaml` 分层模型的性价比

## 两套框架何时用

- **写作任务** → 六类素材框架(`material/`):①原创金句 ②亲历复盘 ③外部权威 ④真实案例 ⑤框架心智模型 ⑥数据趋势
- **产品决策** → 五维工作框架(`_wiki/` 标签检索):市场/技术/产品/人/框架

遇到问题先查 [FAQ 与避坑](faq.md)。
