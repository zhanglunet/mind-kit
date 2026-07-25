# evaluation/ —— 检索与质量回归基线

> 机制:golden-case 回归评测体系。
> 全部自行实现。核心约定:**每摄入一轮真实材料,就沉淀一对回归 case;基线只增不减。**

## 两类 case,两个 runner

| 类型 | runner | case 断言 | 度量 |
|---|---|---|---|
| 检索 | `scripts/evaluate_search.py` | `expected_top1` / `expected_in_top3` / `forbidden_top1`(干扰分离)/ `expect_no_results`(编造实体必须零命中);brain 后端另有 `expected_cite` / `forbidden_cite` | Top-1 / Top-3 / **MRR ≥ 0.75** |
| 质量 | `scripts/evaluate_quality.py` | `required_tokens`(必须出现,**含限定语原文**如「不据此推断…」)/ `forbidden_tokens`(过度推断句不得出现) | 全过 / 有败 |

> 写质量 case 放心用「required=限定语全句 + forbidden=其中的断言子串」组合(如 required「不据此推断转型已经成功」+ forbidden「转型已经成功」):runner 会先遮蔽 required 的出现位置再查 forbidden,限定语内的子串不算违规,**只有在限定语之外独立出现才失败**——这正是"认知边界"断言的本意。

## 跑法

三个检索后端:`fixture`(冻结的旧参考打分器,作对比基准)/ **`local`**(searchlib 新栈:bigram 索引 + 同义扩展 + 三通道 RRF)/ `brain`(真实引擎 HTTP)。

```bash
# 冒烟基线(合成语料,CI/pre-push 自动跑,pytest 已接线;local 后端也须全过——不回退门禁)
python3 scripts/evaluate_search.py evaluation/fixtures/retrieval_smoke.json
python3 scripts/evaluate_search.py evaluation/fixtures/retrieval_smoke.json --backend local
# 难基线(P1-1 量化提升证据:旧 3/6 MRR 0.4 → 新 6/6 MRR 1.0;pytest 锁定"旧败新过")
python3 scripts/evaluate_search.py evaluation/fixtures/retrieval_hard.json --backend local
python3 scripts/evaluate_quality.py evaluation/fixtures/quality_sample/cases.json \
  --base evaluation/fixtures/quality_sample

# 真实 vault 回归(本机,brain-server 先跑起来;case 在内容库,文件名按 round<N> 约定)
python3 scripts/evaluate_search.py ../mind-vault/evaluation/round1_示例_retrieval_cases.json --backend brain
python3 scripts/evaluate_quality.py ../mind-vault/evaluation/round1_示例_quality_cases.json --base .
```

## 存放约定(双库)

- **代码库 `mind/evaluation/fixtures/`**:只放**合成**语料与样例——自包含、无个人内容、CI 可确定性复现。
- **内容库 `mind-vault/evaluation/`**:真实 case(问题与期望页含个人知识,永不进代码库)。
  命名照抄对方的好习惯:`round<N>_<材料名>_{retrieval,quality}_cases.json`。

## 三条纪律

1. **基线只增不减**:新一轮优化必须同时通过历史全部 case;删 case 需书面说明理由。
2. **摄入即沉淀**(CLAUDE.md Ingest 工作流第 6 步):每轮真实摄入补 1-2 条 case——
   检索 case 锁"这轮学到的东西能被搜到",质量 case 锁"没把前瞻写成事实"。
3. **评测绑定架构决策**:检索类改动(P1-1)合并前必须让本基线跑出可量化提升;
   隐含语义查询失败时,先改查询扩展与索引,再考虑向量检索。
