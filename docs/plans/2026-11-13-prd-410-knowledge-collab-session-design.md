# PRD-410/T1：知识共建会话 设计（多人同屏整理同一批知识，入库/修订带署名，未接受不进个人 Wiki）

> trend issue #1970。来源：2026-11-13 GitHub 趋势日报（digests/2026-11-13.md），用户 23/23 逐条采纳。
> 设计日：2026-11-13 · 目标仓库：zhanglunet/mind-kit
> 状态：T1 设计草案，待评审。仅设计文档（纯加法 .md）；内核（T2）、闸门（T3）、划界断言（T4）、验收试运行（T5）按本设计后续落地。
> 示例全部虚构占位，不出现真实内部主机名、IP、账号或密钥。

## 0. PR 门槛自查（repos.yaml default_pr_gate）

| 门槛 | 落实 |
|---|---|
| require_integration_point | **接入点：知识入库/修订提出 之后、个人 Wiki 出口之前**——T2 以 `propose/accept/reject` 会话原语 + `outlet` 出口包装供 个人 Wiki 流程在出口前调用；只把已接受（accepted）的改动写进下游 |
| no_missing_channel | 只消费既有 知识条目 产物结构注入；署名/时间/接受状态写本地 JSONL 会话日志（路径注入文件落库）；同屏=同一份日志回放视图，零新外部渠道、零真实外呼 |
| no_duplicate_module | main 上同类模块盘点：PRD-387（验证台）。**本条不另起 知识引擎**：只管"改的过程看得见"——谁改的、改了什么、接受没有 |
| impl_requires_devlog | T2~T5 实现 PR 各附 devlog 开发记录+合规核对；会话日志落 JSONL 文件（路径注入），不只存内存 |

## 1. 红线

| # | 红线 | 落地方式 |
|---|---|---|
| R1 | **未接受的改动不进 个人 Wiki** | 每条改动先经会话提出（propose）→ 接受（accept）才生效；个人 Wiki 出口只收 accepted；rejected/proposed 一律拦在下游外留痕 |
| R2 | **改动带署名** | 每个会话事件（propose/accept/reject）必须带 author+at；缺一 SESSION_INCOMPLETE 拒绝入账——"谁改的留名" |
| R3 | **会话日志 append-only 可回放** | 事件流 JSONL 只增不删不可改写；`replay(events)` 对同一事件流两遍回放逐条一致（确定性）；破坏 LEDGER_DRIFT 显形 |
| R4 | **状态机封闭** | proposed→accepted/rejected 单向；重复接受、接受/拒绝不存在的条目、对 rejected 再接受均 SESSION_STATE_CONFLICT 显形拒绝 |
| R5 | 占位符纪律 | T5 检查覆盖本文件 |
| R6 | 实现 PR 只开不合并 | 等用户 review |

## 2. 借鉴对象、许可证与不复用红线

zed-industries/zed（双许可证含 GPL-3.0，实测）——只借鉴多人实时协作形态，绝不复用代码；vercel-labs/agent-browser + agent-desktop（Apache-2.0）agent 操作真机形态；CopilotKit/OpenBot（MIT）动作事前已定、事后已记录形态。零代码零文本复用，不引入原仓依赖。

## 3. 与既有机制划界

| 维度 | PRD-410（本条） | PRD-387（验证台） | 收件箱机制 | 重放包机制 |
|---|---|---|---|---|
| 管什么 | **改的过程看得见** | 知识可复现验证 | 等人拍板的异步待办 | 重放可复算 |
| 比对 | 改动 vs 接受状态 | 无 | 无 | 无 |
| 关系 | 个人 Wiki 出口前的现场 | 被会话消费 | 下游（本条不碰） | 相邻不相干 |

## 4. 会话设计

### 4.1 事件 schema（T2 预埋）

```json
{"schema": "knowledge-collab-session/v1",
 "events": [{"seq": 1, "event": "propose",
   "entry_id": "e-001",
   "kind": "intake",
   "author": "editor-a（占位）",
   "at": "2026-11-13T09:00:00Z",
   "payload": {"target": "知识[9]（占位）", "change": "入库条目（占位）"},
   "status": "proposed"},
  {"seq": 2, "event": "accept", "entry_id": "e-001",
   "author": "editor-b（占位）", "at": "…", "status": "accepted"}]}
```

### 4.2 流程（确定性）

提出改动（propose 带署名）→ 同屏可见（日志回放视图）→ 接受/拒绝（accept/reject 带署名）→ 个人 Wiki 出口只收 accepted（`outlet` 包装）→ 全过程落 JSONL append-only。

## 5. 失败闸门（T3 落地）

| 错误码 | 触发 | 行为 |
|---|---|---|
| SESSION_INCOMPLETE | 会话事件缺 author/at/entry_id 或 event 词表外 | 拒绝入账 |
| SESSION_STATE_CONFLICT | 状态机违规（重复接受/unknown id/rejected 再接受） | 显形拒绝 |
| LEDGER_DRIFT | 会话日志被删/改首条/accepted 条目无 accept 事件 | 显形拒绝 |

## 6. 衔接

T2 内核（propose/accept/reject + CollabSessionLedger JSONL + outlet + replay）；T3 闸门（append_only+accept 双向对账+出口拦截+一票否决，ERROR_CODES 随模块导出）；T4 划界（标准库-only 钉值+借鉴仓零符号仅代码标识符扫描+R1~R4 红线钉值）；T5 验收（全链两遍逐字节一致+失败演练+链复跑子进程实测+文档无密钥）。

## 7. 开放问题（留待评审/T2）

1. accepted 条目是否要求 accept 人 ≠ propose 人（倾向不强制——单人会话合法，留 T2 按不强制实现）；
2. 回放视图的排序口径（倾向按 seq 稳定排序——待 T2）。

## 8. 领域备注

- 知识带来源+署名落账：不可溯源的知识在会话里当场可见，Wiki 只留会话里确认的知识。

