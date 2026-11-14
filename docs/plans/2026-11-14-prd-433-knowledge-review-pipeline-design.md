# PRD-433/T1：知识条目评审流水线 设计（规则先行、模型后判——知识条目草稿 成稿前过确定性评审流水线）

> trend issue #2085。来源：2026-11-14 GitHub 趋势日报（digests/2026-11-14.md），用户 23/23 逐条采纳。
> 设计日：2026-11-14 · 目标仓库：zhanglunet/mind-kit
> 状态：T1 设计草案，待评审。仅设计文档（纯加法 .md）；内核（T2）、闸门（T3）、划界断言（T4）、验收试运行（T5）按本设计后续落地。
> 示例全部虚构占位，不出现真实内部主机名、IP、账号或密钥。

## 0. PR 门槛自查（repos.yaml default_pr_gate）

| 门槛 | 落实 |
|---|---|
| require_integration_point | **接入点：知识条目草稿 成稿/提出之后、个人 Wiki 出口之前**——T2 以 `run_pipeline(draft, judge_fn)` + `outlet` 供 个人 Wiki 流程在出口前调用；评审结论 blocked 的草稿不进下游 |
| no_missing_channel | 只消费既有 知识条目草稿 草稿结构注入；确定性规则=本地纯函数（数字复算/口径检查/引用核对，可复算零外呼）；LLM 判定=注入式 judge_fn 只判规则命中候选（不自由发挥、确定性计算不交给模型）；评审结论写本地 JSONL 账本（路径注入文件落库），零新外部渠道 |
| no_duplicate_module | main 上同类模块盘点：PRD-387（验证台）/PRD-359~372（收件箱）/PRD-410（协同会话）。**本条不另起 知识引擎**：只管「成稿前的规则先行评审」——规则扫候选、LLM 判命中、结论落账 |
| impl_requires_devlog | T2~T5 实现 PR 各附 devlog 开发记录+合规核对；评审结论落 JSONL 文件（路径注入），不只存内存 |

## 1. 红线

| # | 红线 | 落地方式 |
|---|---|---|
| R1 | **不通过的草稿不进 个人 Wiki** | 流水线结论=pass/blocked 二值：存在 LLM 确认的规则命中 → blocked；出口只放行 pass |
| R2 | **规则先行、模型后判** | 确定性规则（数字复算/口径检查/引用核对）本地纯函数扫全稿出候选（可复算可追溯逐行定位）；judge_fn 注入式只判候选 confirmed/false_positive——确定性计算不交给模型，LLM 不自由发挥 |
| R3 | **三件套机器可读落账** | 每次评审 {review_id, draft_id, candidates, judgments, verdict} 落 JSONL 账本；缺件 REVIEW_INCOMPLETE 拒绝入账；append-only |
| R4 | **候选必须全判** | 存在未判候选即拒绝落账（不漏判）；verdict 与判定双向一致（有 confirmed 却 pass = REVIEW_VERDICT_MISMATCH） |
| R5 | 占位符纪律 | T5 检查覆盖本文件 |
| R6 | 实现 PR 只开不合并 | 等用户 review |

## 2. 借鉴对象、许可证与不复用红线

alibaba/open-code-review（Apache-2.0，实测）——确定性流水线+LLM 双轨、逐行批注形态；google/elephant-goldfish-model（Apache-2.0，实测）——评审对象扩到设计形态。零代码零文本复用（复用需署名，本链零复制），不引入原仓依赖。

## 3. 与既有机制划界

| 维度 | PRD-433（本条） | 验证台（PRD-387） | 收件箱/会话（PRD-359~372（收件箱）） |
|---|---|---|---|
| 管什么 | **成稿前规则先行评审** | 结论可复现验证 | 等人拍板/改的过程 |
| 比对 | 草稿 vs 确定性规则+LLM 判定 | 结论 vs 复现 | 无 |
| 关系 | 个人 Wiki 出口前的关口 | 相邻不相干 | 下游（本条不碰） |

## 4. 流水线设计

### 4.1 草稿与结论 schema（T2 预埋）

```json
{"schema": "knowledge-review-pipeline/v1",
 "draft": {"draft_id": "d-001",
   "lines": [{"no": 1, "kind": "number",
     "text": "指标=42（占位）", "num": {"stated": 42, "recomputed": 41}},
     {"no": 2, "kind": "text", "text": "含旧口径词（占位）"},
     {"no": 3, "kind": "reference", "text": "见 [ref:R9]（占位）"}],
   "references": ["R1"]},
 "candidates": [{"rule_id": "R-NUM-RECALC", "line": 1}],
 "judgments": [{"rule_id": "R-NUM-RECALC", "line": 1,
   "verdict": "confirmed|false_positive", "note": "…（占位）"}],
 "verdict": "blocked|pass"}
```

### 4.2 流程（确定性）

确定性规则扫全稿出候选（数字复算=stated≠recomputed；口径检查=命中旧口径词表；引用核对=悬空 [ref:*]）→ judge_fn 逐候选判 confirmed/false_positive → 全判齐才落账 → 有 confirmed 即 blocked → 个人 Wiki 出口只收 pass；逐行批注=judgments 带 line 定位。

## 5. 失败闸门（T3 落地）

| 错误码 | 触发 | 行为 |
|---|---|---|
| REVIEW_INCOMPLETE | 三件套缺件/候选未全判/词表外 | 拒绝入账 |
| REVIEW_VERDICT_MISMATCH | 有 confirmed 却 pass（或反之） | 显形拒绝 |
| LEDGER_DRIFT | 账本被删/改首条 | 显形拒绝 |

## 6. 衔接

T2 内核（三条确定性规则+run_pipeline+ReviewPipelineLedger+outlet）；T3 闸门（append_only+verdict 双向对账+全判齐+一票否决，ERROR_CODES 随模块导出）；T4 划界（标准库-only 钉值+借鉴仓零符号仅代码标识符扫描+R1~R4 红线钉值）；T5 验收（全链两遍逐字节一致+失败演练+链复跑子进程实测+文档无密钥）。

## 7. 开放问题（留待评审/T2）

1. blocked 判定口径（倾向：任一 confirmed 即 blocked，无灰度——待 T2）；
2. judge_fn 的输入形状（倾向：逐候选 dict（rule_id/line/文本摘录），返回 verdict+note——待 T2）。

## 8. 领域备注

- 知识带来源+署名落账：不可溯源的知识在会话里当场可见，Wiki 只留会话里确认的知识。

