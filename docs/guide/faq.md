---
title: FAQ 与避坑
---

# FAQ 与避坑

> 汇总 PRD §11 的 12 条风险与脚本的真实报错场景。红线只有三条:**LLM 不改编译引擎的领地、原始来源永不修改、todo 处理完进 archive 不回 clippings。**

## 理念与流程

**Q:要不要先花几周把库整理好再开始用?**
不要。这是 R1 头号坑:"先整理后使用"会陷入永远做不完的整理。先接一个真实写作/决策任务,让 AI 从现有积累里挖宝,库在使用中自然长大。

**Q:todo 处理完的文章放哪?**
移入 `raw/archive/`,**绝不移回 `raw/clippings/`**。clippings 在 watch 范围内,移回去会被当成新文件再次编译,产生重复 Wiki 条目(R2)。

**Q:Query 得到的好答案怎么处理?**
存入 `_wiki/outputs/` 并在 `log.md` 记一笔。洞见留在聊天记录里就是流失(R6)。

**Q:为什么 LLM 不能直接改 `_wiki/summaries/` 里的错误?**
那是编译引擎的领地(R5)。直接改会和下次编译冲突。正确做法:把修正写进 `_wiki/outputs/`,或修正原始来源后重新编译。

## flomo 相关

**Q:flomo 导出能不能直接丢进编译范围?**
不能(R3)。flomo 每次导出是**全量快照**,直接编译会整库重复。永远走增量脚本:只有 `raw/flomo/delta/` 会被编译,原始导出原样保留。

**Q:`flomo-delta.py` 报"状态文件损坏"怎么办?**
按提示操作:若 `.processed_hashes.json` 曾提交进 git,用 git 历史恢复;**不要直接删除**——删除后下次运行会把全部历史笔记当作新增,造成大规模重复编译。可先备份损坏文件再手工修复 JSON。

**Q:报"不是 UTF-8 编码,本次已跳过"?**
该文件被安全跳过(不会写入乱码),其笔记未记指纹。用 `iconv -f GBK -t UTF-8 旧文件 > 新文件` 转码后重跑,笔记会自动补上。

**Q:delta 文件生成了,但没被编译进 Wiki?**
检查编译引擎是否满足"sources 优先于父目录 ignore"的语义(PRD §4.4 硬标准 5):`config.yaml` 同时有 `ignore: raw/flomo` 和 `sources: raw/flomo/delta`,若引擎按 ignore 优先解析,delta 会被静默排除。这是换引擎时的必验项(PRD §10.2 验收清单)。

**Q:一条笔记改了几个字,会重复进库吗?**
会作为"新增"再次输出(指纹按内容哈希)。这是全量快照比对的固有代价,健检(Lint)会发现近似重复并建议合并。

## 脚本与自动化

**Q:`auto-archive.sh` 一直说"尚无编译产物的 commit 记录"?**
两种可能:① 还没编译过或编译后没有 commit——先 `sage-wiki compile` 并确认 auto_commit 生效;② `_wiki` 产物路径与脚本 pathspec 不一致——脚本只认 `_wiki/summaries|concepts|entities` 下 `.md` 的提交。

**Q:为什么有的剪藏一直不被归档?**
归档判据是"已提交 git 且编译 commit 后无任何改动"。未提交(untracked)或编译后被改过的文件会一直保留——这是刻意设计:失败方向永远是"多留一周",绝不把没编译过的文章丢进不再编译的 archive。

**Q:忘了先 `git init` 就编译了?**
补 `git init && git add -A && git commit` 即可。auto_commit 与归档脚本从下次编译起正常工作;已编译内容不受影响。

## 成本与安全

**Q:LLM 调用成本怎么控?**
四层护栏(R11):高频任务用小模型(summarize/extract/lint 用 Haiku 级)、忽略清单不送 API、只编译增量、月度预算上限内优先保留 query/write。

**Q:API Key 应该放哪?**
环境变量注入,绝不写进仓库文件(R9)。`.gitignore` 已排除常见密钥文件。

**Q:怎么备份?**
Git 本地版本化 + 远端私有仓库或加密同步盘做异地备份(R10)。纯 Markdown 意味着迁移 = 拷贝目录。

**Q:发布文档站会泄露我的笔记吗?**
不会,前提是遵守发布边界:只有 `site/`(项目文档)会部署,`raw/`、`_wiki/`、`material/`、`writing/` 永不进入发布目录。知识库内容本地优先是 PRD §2.2 的明确非目标。详见[发布指南](deploy.md)。

**Q:库越来越大会变慢/变贵吗?**
方案甜点区是 100–10,000 篇高信号来源(R12)。超过数百页启用混合检索(BM25+向量,`config.yaml` 可调权重);接近上限考虑分库。
