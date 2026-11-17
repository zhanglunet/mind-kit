# PRD-515/T1：知识条目技能契约设计（契约五件套——工具清单/输入输出 schema/前置条件/失败语义/回退）

> trend issue #2495。来源：2026-11-17 GitHub 趋势日报（digests/2026-11-17.md），用户 2026-11-17 拍板采纳。
> 设计日：2026-11-17 · 目标仓库：zhanglunet/mind-kit
> 状态：T1 设计草稿，待评审。仅设计文档（纯加法 .md）；契约 schema+落账（T2）、契约校验（T3）、划界断言（T4）、验收试运行（T5）按本设计后续落地。
> 示例全部虚构占位，不出现真实内部主机名、IP、账号或密钥。

## 0. PR 门槛自查（repos.yaml default_pr_gate）

| 门槛 | 落实 |
|---|---|
| require_integration_point | **接入点：知识条目草稿调用前（executor 派发之前）**——T2 以 `validate_call(contract, call_params)` 供调用流程在调用技能前校验；无契约的技能不进个人 Wiki |
| no_missing_channel | 只消费技能注册表与调用参数（本地 dict 注入）；契约五件套写本地 JSONL 落账（路径注入文件落库），零新外部渠道 |
| no_duplicate_module | main 上同类模块盘点：knowledge_collab_session（协同会话）/knowledge_review_pipeline（评审流水线）/knowledge_supervision_bench（监督回路）。**本条不另起执行循环**：只管「调用那一刻」的契约校验——调什么、传什么、失败返回什么 |
| impl_requires_devlog | T2~T5 实现 PR 各附 devlog 开发记录+合规核对；契约校验结果落 JSONL 文件（路径注入），不只存内存 |

## 1. 红线

| # | 红线 | 落地方式 |
|---|---|---|
| R1 | **无契约的技能不进个人 Wiki** | 每个技能必须先注册契约（工具清单+输入输出 schema+前置条件+失败语义+回退）；未注册契约的技能调用直接拒绝 |
| R2 | **契约五件套缺一不可** | 工具清单（能调什么）/ 输入输出 schema（传什么、回什么）/ 前置条件（什么情况下能调）/ 失败语义（调不出来返回什么，绝不瞎编）/ 回退（失败了走哪条路）——缺一 CONTRACT_INCOMPLETE 拒绝注册 |
| R3 | **失败返回显式「未算出」** | 调不出来的技能返回显式 `NOT_COMPUTED`（而非编数字、静默丢活、或瞎编结果）；T3 校验拦下含糊的失败返回 |
| R4 | **回退先问人** | 前置条件不满足（如口径缺失）→ 回退=先问人（写收件箱），不猜不补 |
| R5 | 占位符纪律 | T5 检查覆盖本文件 |
| R6 | 实现 PR 只开不合并 | 等用户 review |

## 2. 借鉴对象、许可证与不复用红线

kajisho5/ffmpeg-skill（MIT，实测）——42 工具+机器可读契约+MCP 形态；mvanhorn/last30days-skill（MIT，实测）——契约管"从哪来、怎么合成"；google-research/paper-orchestra（Apache-2.0，实测）——契约管分工与交接；ag-ui-protocol/ag-ui（MIT，实测）——调用契约的另一面。零代码零文本复用，不引入原仓依赖。

## 3. 与既有机制划界

| 维度 | PRD-515（本条） | PRD-478~500（技能评估） | PRD-419（评审流水线） | PRD-373（验证台） | PRD-396（协同会话） |
|---|---|---|---|---|---|
| 管什么 | **调用那一刻的契约校验** | 技能包健不健康 | 产物对不对 | 结论真假 | 改的过程 |
| 比对 | 调用参数 vs 契约 schema | 包 vs 质量标准 | 草稿 vs 规则+LLM | 结论 vs 复现 | 改动 vs 接受状态 |
| 关系 | 调用前的上游关口 | 相邻（评包不评调用） | 下游（本条不碰） | 相邻不相干 | 相邻不相干 |

## 4. 契约五件套 schema（T2 预埋）

```json
{"schema": "knowledge-skill-contract/v1",
 "contract_id": "contract-knowledge-001",
 "skill_name": "knowledge_skill（占位）",
 "tools": ["knowledge_read（占位）", "knowledge_compute（占位）"],
 "input_schema": {"input": "…（占位）", "version": "v1（占位）"},
 "output_schema": {"conclusion": "string", "cited": ["knowledge（占位）"]},
 "preconditions": {"schema_version_present": true},
 "failure_semantics": "NOT_COMPUTED",
 "fallback": "ask_human"}
```

## 5. 校验流程（确定性）

技能注册契约（五件套齐才收）→ 调用前校验（call_params vs input_schema + 前置条件）→ 校验通过 → 执行技能 → 失败返回显式 `NOT_COMPUTED` → 评审通过后结论进个人 Wiki。无契约的技能调用 → CONTRACT_MISSING 拒绝；校验不过 → CONTRACT_VALIDATION_FAILED 拒绝。

## 6. 失败闸门（T3 落地）

| 错误码 | 触发 | 行为 |
|---|---|---|
| CONTRACT_MISSING | 无契约的技能调用 | 拒绝（R1） |
| CONTRACT_INCOMPLETE | 五件套缺一 | 拒绝注册（R2） |
| CONTRACT_VALIDATION_FAILED | 调用参数与 input_schema 不匹配/前置条件不满足 | 拒绝调用 |
| CONTRACT_FAILURE_AMBIGUOUS | 失败返回不含显式 NOT_COMPUTED | 拦下含糊的失败返回（R3） |

## 7. 衔接

T2 契约 schema+落账（ContractLedger JSONL+validate_call）；T3 契约校验（四码闸门）；T4 划界断言（无契约不进个人 Wiki+借鉴仓零符号+AST 零网络）；T5 验收试运行（真实调用按契约跑一遍+失败语义演练+链复跑+文档无密钥）。

## 8. 开放问题（留待评审/T2）

1. 契约存储路径（倾向 data/skill-contracts/ 按技能名一文件——待 T2）；
2. 回退="先问人"的落点（倾向写收件箱类既有模块——待 T2）。
