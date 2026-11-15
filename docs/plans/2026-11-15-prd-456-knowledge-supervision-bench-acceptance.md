# 知识监督台验收试运行记录（PRD-456/T5）

> 来源：trend issue [#2204](https://github.com/zhanglunet/trend/issues/2204)（[PRD-456/T5] 知识监督台验收试运行）；PRD 全文：`zhanglunet/trend` 仓库 `adopted/PRD-456-mind-kit-knowledge-supervision-bench.md`。
> 状态：验收试运行记录（T5），只开 PR 不合并，等 review。
> 依据：T1 设计（`docs/plans/2026-11-15-prd-456-knowledge-supervision-bench-design.md` §7）+ T2 最小实现 + T3 闸门 + T4 划界断言；本轮未改 T1–T4 的设计与代码，只新增验收脚本与验收测试。

## 1. 验收结论

**全链跑通。**来源不明的知识在整理时就被批注发回，Wiki 只留人点头过的知识。

## 2. 跑了什么

验收脚本 `scripts/knowledge_supervision_acceptance.py`（仓库根执行，内存里的合成占位数据，零网络零子进程），5 个场景全过：

| 场景 | 结果 | 内容 |
|---|---|---|
| happy-path-full-chain | 通过 | k-001：整理 → 批注（换来源）→ 发回 → 改回 v2（来源 A→B）→ 点头 → 过闸 → 入账；进度 drafted/returned/revised/approved 四步齐全，旧批注带到新版；出口只放行已点头的 k-001 v2，k-002 待审与无记录的 k-003 被拦、整批 vetoed |
| unapproved-blocked | 通过 | 待审 k-001 拦下（NOT_APPROVED）；无记录的 k-009 拦下并记一条 SUPERVISION_OUTLET_BYPASS 告警；一批有拦即整批 vetoed |
| old-approval-does-not-admit-new-version | 通过 | v2 已点头放行；v3 以 VERSION_MISMATCH 拦下，须重新点头 |
| approve-with-unresolved-refused | 通过 | 有未处理批注却点头 → SUPERVISION_VERDICT_MISMATCH 拒绝；发回与点头同一次 → 同样拒绝；被拒绝的记录拒绝入账 |
| three-records-complete | 通过 | 链上 4 条记录：进度 / 批注 / 发回反馈齐全；账本 4 条、最新一条为 approved v2；verdict=returned 却无发回轮次的记录拒绝入账 |

## 3. 测试结果

- 本地：`python3 -m pytest tests/ -q`——**72 passed**（T2 + T3 + T4 + 本轮新增 T5 验收测试，含 T2–T4 回归；隔离目录跑新模块 + 新测试，全量套件以 CI 为准）。
- 验收脚本直接跑：`python3 scripts/knowledge_supervision_acceptance.py`——退出码 0，verdict“全链跑通”，5/5 场景通过。
- 未发现本次改动引入的失败；未触碰 T1–T4 已有模块，无基线红需要说明。

## 4. 试运行记录（合成占位数据）

- 试运行对象：知识 k-001（来源占位、标签占位），全程走监督台：批注发回一次、改回一版、点头一次。
- 未点头的知识不进个人 Wiki：待审、已发回、无记录三种状态在闸门与出口两处均被拦下留痕；无记录的还记一条出口绕过告警；一批里有一条被拦即整批 vetoed，无例外通道。
- 超时未裁决不自动放行：一直 pending 的知识过闸即拦下（NOT_APPROVED）。
- 批注与反馈全程留痕：进度、批注、发回反馈三类记录齐全，账本 JSONL append-only（路径注入）；同一知识多版本之间批注不丢失。

## 5. 红线

- 监督台不验真假、不产生新知识：入账内容与入项逐字节一致；站不住的内容仍只 pending，不出真假结论。
- 人只批注和裁决，不下场改知识内容；改内容只能由 agent 经改回回路完成、版本 +1。
- 未点头的知识不进个人 Wiki，无例外通道、无绕过开关。
- 文档与示例全为合成占位，无真实内部主机名、IP、账号或密钥。
- 实现类 PR 只开不合并，等用户 review。

## 6. 借鉴声明

- backnotprop/plannotator（Apache-2.0）、ag-ui-protocol/ag-ui（MIT）：只借监督回路形态；本轮新增代码为原创，未复用其代码。
- Tencent/LoopForge（无 LICENSE）：只借人工批准门形态，绝不复用其文本或代码。
