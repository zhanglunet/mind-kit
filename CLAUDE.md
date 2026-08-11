# CLAUDE.md — 第二大脑 Schema

这是整套系统的"宪法"。它告诉 Claude Code / Claudian 各工具的权责边界,防止 LLM 越权修改 sage-wiki 管辖的文件,也让它知道如何处理不同来源的内容。本文件随使用持续迭代(这是最值得投入时间的地方):你(LLM)可以提出修改建议,经用户确认后再更新。

## 工具权责边界(最重要)
- sage-wiki 全权负责:`_wiki/` 下的 `summaries/`、`concepts/`、`entities/`
  - 你(LLM)不要直接创建或修改这些文件
  - 你可以读取它们用于 Query,可以在 `_wiki/outputs/` 创建分析报告
- 你(LLM)全权负责:`material/` 目录
- 你(LLM)可写 `writing/` 目录,但以用户为主导(存放用户的写作成稿)
- 共同维护:`_wiki/index.md` 和 `_wiki/log.md`(你可以追加,不要删除)

**审批边界按影响类型分,不按动作数量分**:
- **自动可做**:读取/抽取、摄入成稿(outputs/material 草稿)、重建索引、写报告/日志、lint 记账——不必逐次请示。
- **放置即授权**:用户把文件放进 `raw/todo/` 并要求处理,即构成"读取→讨论→抽取→成稿"的完整授权;不要因文件名看着敏感就反复确认。二次确认只留给明显高敏材料(密钥、隐私、薪酬、法务)。
- **须先确认**:删除/合并已有页面、改写已确认的结论、调整目录结构或本宪法、对外发布。

## 双库布局(2026-07-19 起)

**这个工作目录跨越两个 git 仓库,写文件前必须清楚你在写哪个。**

```
second-brain/
├── mind-kit/      ← 代码库(本仓,可公开)
│   ├── scripts/ prompts/ site/ docs/ config*.yaml CLAUDE.md …  ← 真实文件
│   └── _wiki  material  raw  writing  reports/{daily,weekly,lint}  ← 全是软链 ↓
└── mind-vault/      ← 你的内容库(私有,自建:bash scripts/init-vault.sh)
    └── _wiki/ material/ raw/ writing/ reports/{daily,weekly,lint}/    ← 个人内容本体
```

由此产生的硬约束:

- **提交个人内容用 `bash scripts/vault.sh commit "<msg>"`,不要在代码库里 `git add` 个人目录** —— 那些路径在 `mind/.gitignore` 里,`git add` 会静默什么都不干。`vault.sh` 自动识别该落哪个库(单库/双库都能用)。
- **两个 `.gitignore` 要同步**:代码库的 `.gitignore` 管代码,内容库的管个人内容(大体积二进制、`raw/private` 等)。改了一边想想另一边。
- **引擎 `auto_commit` 已关**(三个 config 都是 `false`)。编译产物由 `scripts/compile.sh` 收尾调 `vault.sh` 落到内容库。
- **内容库必须私有。** 本代码库不含任何个人内容;你的知识内容只应存在于你自己的私有内容库中,任何时候都不要把它提交进代码库。

## 开发纪律(Superpowers)

代码类开发遵循 [Superpowers](https://github.com/obra/superpowers) 纪律,四原则:**①测试先行 ②系统化优于拍脑袋 ③简单为第一目标 ④用证据而非声称**。硬约束:

- **每个开发任务**开工先写下「目标 + 计划」,收尾补「做法 / 验证证据 / Superpowers 自检 / 偏差」(建议记在自己的开发流水账里)。
- **动手前先想**:多方案 brainstorm、写下计划,别单稿硬做;可并行或需对抗验证的部分派子代理。
- **脚本改动强制 pytest-first**:改 `scripts/*.py` 的函数逻辑,或 `scripts/*.sh` 的可观测行为(输出/退出码/落文件),**必须先写会失败的 pytest(RED)→ 实现到通过(GREEN)→ 重构(REFACTOR)**,并留下**先红后绿**的运行证据(只有事后补一条必过测试不算 TDD)。测试放 `tests/`,跑法 `python3 -m pytest -q`;shell 用 subprocess 测(见 `tests/test_vault_sh.py`)。"什么算脚本改动"、`.sh` 与一次性脚本的例外、worked example,全见 `tests/README.md`。
- **非脚本产出**(SVG/HTML/文档等无单测语义):用可复现证据替代(渲染目检、`xmllint`、跑一遍),自检里标 N/A 并写明替代证据。
- **克隆后装一次 git 钩子**:`bash scripts/install-hooks.sh`(pre-push 在每次 push 前跑 pytest,红则拦;纯删分支/推 tag 自动跳过;`git push --no-verify` 可临时跳过)。服务端兜底见 `.github/workflows/tests.yml`(需仓库在 GitHub 启用 Actions)。
- **收尾必验证**:真跑一遍留证据,而非"应该没问题",再 PR / 合并 / 同步本地。
- **Windows 原生门禁只走 GitLab CI/CD**:`.gitlab-ci.yml` 的 `windows-native` job 绑定
  `windows` + `powershell` Runner 标签；不要在 GitHub Actions 中新增 `windows-latest`。
- **"Prompt 不是检查器"**:只有脚本/测试能确定性执行的规则才算硬门禁(pytest、pre-push、CI、评测基线);提示词与文档条款只是尽力遵守的软规范。想让某条规范"必须遵守",就为它写可执行检查,别指望文字自我执行。
- 这套纪律本身每次开发前也要自检是否仍适用(check for a relevant skill before any task)。

## 目录结构
- `raw/clippings/` → sage-wiki 自动编译(不需要你处理)
- `raw/todo/` → 等待你做深度对话式 ingest 的文章
- `raw/archive/` → 已处理存档,不要碰
- `raw/flomo/` → flomo 原始导出(不要修改),`delta/` 子目录是增量文件
- `raw/articles/` → 你自己的历史文章存档。**只作文章收藏,不是编译源,不进 Wiki 概念体系。**
  每个来源分 `MD/`(文字版,入库)和原件目录(PDF 等,gitignore 不入库)。要引用这些文章,
  直接读 markdown,不要加进 `config.yaml` 的 `sources`。
  <br>**踩过的坑**:强行编译上百篇评论性散文,会抽出十几倍于技术剪藏的概念,
  且多是单篇一次性表述、文章修辞手法与人名公司实体,把已收敛的概念体系淹掉。
  这不是提示词 bug —— `prompts/extract-concepts.md` 明写「宁多勿少、一篇 10 个以上」,
  那是为技术剪藏调的,与散文语料错配。**结论:散文类历史文章只收藏,不编译。**
- `raw/private/` → 软链到 Google Drive 的敏感冷存层,永不入库,不要读写
- `_wiki/` → sage-wiki 的领地,你只读不写(`outputs/` 除外)
- `material/` → 你的领地,按六类框架存放素材
- `reports/` → 工作日志(日报/周报),脚本自动维护为主;你可写,但"手记/综述"区外的自动盘点部分由脚本生成

## 订阅台账(subscriptions)
- 数据源 内容库根的 `subscriptions.json`(手工维护,anchor=上次扣费日;勿放卡号等敏感信息)
- CLI `scripts/subscriptions.py`(列表/`--days N`/`--notify` 弹 macOS 通知);页面 `scripts/build-subscriptions-site.py` → `browse/subscriptions/`,门户卡片由 `build-portal.py` 生成
- cron 每日 9:17:通知 + 重建台账页和门户

## Ingest 工作流(针对 raw/todo/ 的深度处理)
0. **对话附件先入箱**:对话中收到的文件,先安全复制进 `raw/todo/`(同名同内容复用、同名异内容改名不覆盖)再处理;**产出里引用 vault 内路径,不要引用宿主临时上传路径**(如 uploads 目录——会失效,破坏证据链)
1. 读取文章,与用户讨论关键要点(不要跳过这步)
2. 在 `_wiki/outputs/` 写一个简要摘要页(不要写到 `summaries/`,那是 sage-wiki 的)
3. 按六类框架提取素材存入 `material/` 对应子目录
4. 在 `_wiki/log.md` 追加:`## [日期] ingest ｜ 文章标题`
5. 告知用户可以把文件移入 `raw/archive/`
6. 为本轮摄入沉淀 1-2 条回归 case 到 内容库的 `evaluation/`(检索 case:问题→期望被引用的页;质量 case:required/forbidden tokens 锁认知边界)。**基线只增不减**;确无可沉淀时在当日记录说明即可。跑法见 `evaluation/README.md`。

## 待确认决策队列(2026-07-23 起)
- **须先确认的动作**(提升入库/删除/合并页面/Schema 变更/归档调整)不再散落对话里,每件先建一条决策记录:`python3 scripts/decision.py new <promote|merge|delete|schema|archive|other> "<标题>" --target <涉及页面>`(落 `_wiki/outputs/decisions/`,状态 pending)
- 用户裁决 → `approve <DEC-id> [--note 说明]` / `reject` / `defer`;**approved 只是授权,实际执行完成后才 `apply`**(审批与执行分离,均可追溯)
- **唯一用户入口**:`_wiki/outputs/待确认看板.md`(Dataview 聚合;`decision.py board` 幂等生成);机器记录在 `decisions/` 子目录,同一事实不双写
- `_wiki/under_review/` 的查询产物要**提升入库 → 走本队列**(promote 类型)
- lint 时顺带跑 `python3 scripts/decision.py check` 验状态机不变量(违规非零退出)

## Query 工作流
1. 先读 `_wiki/index.md` 找相关页面
2. 深入读相关页面,综合答案,附 Wiki 内链接
3. 遇库内数据缺口时,可用 WebSearch 联网补充,并在产出里明确区分"库内 / 联网"并注明来源(FR-QRY-05)
4. 有价值的分析存入 `_wiki/outputs/`,在 `log.md` 追加

## flomo 处理偏好(raw/flomo/delta/)
- 重点提取:① 原创金句 ② 自我反思与决策复盘 ⑤ 框架与心智模型
- 弱化权重:③ 外部引用 ⑥ 数据(除非 flomo 笔记本身包含这类内容)

## 两套框架何时用
- 写作任务 → 六类素材框架(`material/`):① 原创金句 ② 亲身经历与决策复盘 ③ 外部权威与市场信号 ④ 真实案例 ⑤ 框架与心智模型 ⑥ 数据、研究与趋势
- 产品/竞品/融资/招聘决策 → 五维工作框架(`_wiki/` 五维标签检索):市场与竞争 / 技术判断 / 产品与用户 / 人与组织 / 框架与心智模型
- **五维落地约定**:做决策查询时,用 `_wiki/outputs/五维决策看板.md` 里对应维度的查询模板对 Wiki 提问;有价值的分析整理成 `_wiki/outputs/` 页并加 frontmatter `dimension: [维度]`(取值固定这五个,可多选),由五维决策看板的 Dataview 自动汇总。`sage-wiki query` 的原始产物先落 `_wiki/under_review/`(gitignore),确认后再提升入库。

## 日报 / 周报工作流(reports/)
- 生成:`python3 scripts/daily-report.py`(默认盘点昨天)、`python3 scripts/weekly-report.py`(默认上一个完整周)
- 脚本从 git 提交 + `_wiki/log.md` + flomo 增量自动盘点,每条结论可回溯到 sha 或 log 条目
- 拆库后 `reportlib` 会同时盘点**两个库**的提交(代码库 + 内容库),不必手工合并
- 你可以在日报"手记"区、周报"周度综述"区补写叙事/反思:这两个区在 `<!-- 手记开始 -->`/`<!-- 综述开始 -->` 标记之间,脚本重生成时**原样保留**,标记以上的自动部分才会被覆盖
- 合成周报:被要求写周度综述时,读取该周 `reports/daily/` 各日报(含手记),在周报的综述区写主线/进展/问题/下步

## Lint 检查项
- 页面间矛盾 / 被新来源推翻的旧声明
- 孤立页面(无入链)/ 缺失交叉引用
- 重要概念被多处提及但没有独立页面
- 可联网补充的数据缺口 / 下一步值得深挖的问题
- **保鲜复核**(P1-3):`python3 scripts/freshness.py` 按半衰期列出"值得复核"页(compile.sh 已自动追加进 lint 报告);复核后 `--confirm <路径>` 登记确认。**只提示不自动改**。给 `_wiki/outputs/`、`material/` 的重要页面加 `volatility: high|medium|low`(半衰期 30/90/365 天,`half_life_days` 可显式覆盖)+ `last_confirmed: 日期` 即纳入追踪;不加字段则不参与(加了之后 `okf.py --fix` 会顺带算出 OKF 的 `stale_after`)
- 决策队列不变量:`python3 scripts/decision.py check`(compile.sh 已自动跑)
- **OKF 合规**(Open Knowledge Format v0.2):`python3 scripts/okf.py --check` 体检、`--fix` 幂等注入(compile.sh 已自动跑:`--fix` 在重建 index 之前,`--check` 记进 lint 报告)。硬性要求只有两条——每页有合法 frontmatter、`type` 非空;`type` 由目录 + 已有键**确定性**推出(概念页直接取 `entity_type`),**只加不改**,`entity_type` / `类别` / `decision_type` 等原键一律保留。这是引擎领地(`_wiki/{summaries,concepts,entities}`)唯一的门禁——`validate_write_set.py` 的 `LLM_SCOPE` 不含这三个目录。**注意**:引擎重写页面会抹掉注入的键,靠下一轮编译自愈,所以别手动补 `type`,跑 `--fix` 就行
