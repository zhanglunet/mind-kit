# PRD-515/T5 开发记录：知识条目技能契约验收试运行（2026-11-17）

> trend issue #2499。承接 T1 设计草稿，复用 501 验证过的契约骨架逻辑。

## 交付

- `tests/test_prd515_t5_contract_acceptance.py`：全链两遍逐字节一致+失败演练三路+链复跑 exit 0+文档无密钥。
- 测试全绿；零网络零子进程；示例全合成占位。

## PR 门槛合规核对（repos.yaml default_pr_gate）

| 门槛 | 落实 |
|---|---|
| require_integration_point | 接入点=知识条目草稿调用前 |
| no_missing_channel | 纯标准库本地 JSONL，零网络零子进程 |
| no_duplicate_module | 只管调用那一刻的契约校验 |
| impl_requires_devlog | 本文件即开发记录 |

## 合规核对

- 无契约的技能不进个人 Wiki（R1，测试钉值）；失败必须显式 NOT_COMPUTED（R3，测试钉值）。
- 示例全合成占位。只开 PR 不合并。
