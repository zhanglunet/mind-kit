# PRD-387/T1：入库知识验证台设计（知识来源复核过才进个人 Wiki）

> trend issue #1891。来源：2026-11-12 GitHub 趋势日报（digests/2026-11-12.md）第 15 条，用户 2026-11-13 指令「拍板」采纳。
> 设计日：2026-11-12 · 目标仓库：zhanglunet/mind-kit
> 状态：T1 设计草案，待评审。仅设计文档（纯加法 .md）；验证台内核（T2）、闸门（T3）、划界断言（T4）、验收试运行（T5）按本设计后续落地。
> 示例全部虚构占位，不出现真实内部主机名、IP、账号或密钥。

## 0. PR 门槛自查（repos.yaml default_pr_gate）

| 门槛 | 落实 |
|---|---|
| require_integration_point | **接入点：知识入库入口（`scripts/build-index.py` 消费 wiki 源文件之前）**——T2 验证台以注入式函数 `verify_knowledge(item, corpus, recheck_fn)` 供入库流程在 build-index 消费前调用；只把 VERIFIED 的知识写进个人 Wiki 源目录 |
| no_missing_channel | 只消费 wiki 源文件形态（corpus 注入）与既有入库入口；复算=对同一语料快照重跑同一来源复核判定（recheck_fn 注入，复访=对语料快照复算零真实外呼）；验证结论写本地 JSONL 账本（文件落库），零新外部渠道 |
| no_duplicate_module | main 上同类模块盘点：build-index.py（索引产出）/build-wiki-site.py（站点渲染）/scripts 既有采集脚本。**本条不另起来源复核**：复算=注入式重跑同一复核判定，来源可复访+quote 逐字回指双 match 才 VERIFIED |
| impl_requires_devlog | T2~T5 实现 PR 各附 docs/devlog/2026-11-13-prd-387-*.md 开发记录+合规核对；账本落 JSONL 文件（路径注入），不只存内存 |

## 1. 红线

| # | 红线 | 落地方式 |
|---|---|---|
| R1 | **知识来源复核过才进 Wiki** | 每条新入库知识先按来源复核验证（来源 URL 在语料快照中可复访 + quote 逐字回指）；复核不过 → UNVERIFIED——不可溯源的知识拦在 Wiki 外 |
| R2 | **验证不产生新知识** | 复算=重跑注入的同一来源复核判定（语料快照只读深拷贝，零真实外呼）；复现不出=UNVERIFIED 不猜不补 |
| R3 | **机器可读落账** | 每次验证 `{item_id, source_url, kind, source_ref, corpus_fingerprint, item, reproduce, verdict}` 八件套落 JSONL 账本；缺任一 BENCH_INCOMPLETE 拒绝入账 |
| R4 | **账本 append-only + 修复二次验证才关闭** | 验证账本只增不删；语料变更后二次验证落新记录，关闭以最新 VERIFIED 为准 |
| R5 | 占位符纪律（URL 一律 example.invalid） | T5 检查覆盖本文件 |
| R6 | 实现 PR 只开不合并 | 等用户 review |

## 2. 借鉴对象、许可证与不复用红线

openai/codex-security（Apache-2.0，实测）+ cloudflare/security-audit-skill（MIT，实测）——只借鉴「发现→验证→修复→再验证」控制面形态；条目 schema 按本仓知识域自研，零代码复用，不引入原仓依赖。

## 3. 与既有机制划界

| 维度 | PRD-387（本条） | build-index.py | build-wiki-site.py |
|---|---|---|---|
| 管什么 | 逐条 **知识可溯源** | 索引产出 | 站点渲染 |
| 比对 | 来源复访+quote 回指 | 无 | 无 |
| 关系 | 入库之前 | 下游消费验证过的源 | 下游 |

## 4. 验证台设计

### 4.1 条目 schema（T2 预埋）

```json
{"schema": "knowledge-verify-bench/v1",
 "items": [{"item_id": "k-001",
   "source_url": "https://kb.example.invalid/note-1（占位）",
   "kind": "note",
   "source_ref": "wiki-source/notes/1.md（占位）",
   "corpus_fingerprint": "sha16:…（语料快照）",
   "item": {"title": "笔记（占位）", "quote": "关键句（占位）"},
   "reproduce": {"source_match": true, "quote_match": true, "detail": "…（占位）"},
   "verdict": "VERIFIED|UNVERIFIED"}]}
```

### 4.2 流程（确定性）

新知识条目 → 重跑同一来源复核判定（注入 recheck_fn，语料快照深拷贝）→ 来源可复访（source_match）+ quote 逐字回指（quote_match）双 match → VERIFIED / 否则 UNVERIFIED → 落账 → Wiki 源目录只收 VERIFIED。

## 5. 失败闸门（T3 落地）

| 错误码 | 触发 | 行为 |
|---|---|---|
| BENCH_INCOMPLETE | 八件套缺一/词表外 | 拒绝入账 |
| BENCH_REPRO_MISMATCH | 声称 VERIFIED 但复现不全（或反之） | 显形拒绝 |
| BENCH_STALE | 语料快照指纹与当前不符 | 拒绝复用旧验证 |

## 6. 衔接

T2 内核（verify_knowledge + JSONL 账本）；T3 闸门（三码+零网络 AST）；T4 划界（标准库-only 钉值+借鉴仓零符号+词表封闭）；T5 样例全链回放+UNVERIFIED 拦截演练+文档无密钥。

## 7. 开放问题（留待评审/T2）

1. corpus_fingerprint 口径（倾向语料条目 canonical JSON sha16——待 T2）；
2. 入库侧接入的强制方式（倾向 verify_items 包装供 build-index 调用方显式接入——待 T2）。
