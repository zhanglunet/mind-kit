# PRD-433/T5 开发记录：知识条目评审流水线 验收试运行（2026-11-14）

## 交付

- `test_prd433_t5_pipeline_acceptance.py`：6 例全绿（本链合计 36 例：T2 12+T3 11+T4 7+T5 6）。
  - 接入点全链演练两遍逐字节一致：草稿→run_pipeline（规则扫候选+judge 判定）→落账→outlet（blocked 拦下）→闸门全 pass。
  - 失败演练显形：blocked 拦截留痕；未全判拒绝且零落账；账本删除 LEDGER_DRIFT。
  - 链复跑子进程实测：T2/T3/T4 复跑 exit 0。
  - 文档无密钥：T1 设计文档拼接 needle 扫描+占位符纪律（R5）。

## PR 门槛合规核对（repos.yaml default_pr_gate）

| 门槛 | 落实 |
|---|---|
| require_integration_point | 接入点全链演练：outlet→pass 进 个人 Wiki，blocked 拦下——T1 §0 接入点语义端到端验证 |
| no_missing_channel | 演练全链本地复算零外呼；唯一子进程是链复跑测试自身，产品代码零子进程 |
| no_duplicate_module | 试运行只消费本链 T2/T3 内核与闸门，不新增模块 |
| impl_requires_devlog | 本文件即开发记录 |

## 合规核对

- 产品代码零网络零子进程（T2/T4 AST 断言钉住）；测试内 subprocess 仅用于链复跑。
- 示例全合成占位，无真实主机名/IP/账号/密钥。R6：本链全部 PR 只开不合并。
