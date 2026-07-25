# tests/ —— 脚本改动的 pytest-first 纪律

本仓脚本改动遵循 **TDD:先写会失败的测试(RED)→ 实现到通过(GREEN)→ 重构(REFACTOR)**。
权威规则见 `CLAUDE.md`「开发纪律(Superpowers)」;本文件讲**怎么落地**。

## 怎么跑

```bash
pip install -r requirements-dev.txt   # 只需一次(装 pytest)
python3 -m pytest -q                   # 跑全部;在仓库根执行
python3 -m pytest tests/test_reportlib.py::test_bucket_of_config_family -q   # 单条
```

`pytest.ini` 已设 `pythonpath = scripts`,所以测试里可直接 `import reportlib`(scripts/ 下**无连字符**的 .py 都能 import)。

## 目录约定

- 测试文件放 `tests/`,命名 `test_<被测脚本>.py`;测试函数 `test_<行为>`。
- 一个纯函数一组断言;涉及文件的用 pytest 的 `tmp_path` fixture,**不碰真实仓库文件**。
- 断言要锁**具体行为与边界**(空输入、占位判空、前缀误伤、顺序敏感),不是"能跑就行"。

## 什么算"脚本改动"(必须 pytest-first)

| 改动对象 | 要求 |
|---|---|
| `scripts/*.py`、`tools/**/*.py` 里的**函数/逻辑** | **强制** RED→GREEN→REFACTOR |
| `scripts/*.sh` 的**可观测行为**(输出/退出码/落文件) | **强制**,用 `subprocess` 跑脚本断言(见 `test_vault_sh.py`);纯 git/网络副作用不可测的部分,至少 `bash -n` 语法 + 一次带断言的实跑,证据记 `开发流水账` |
| 一次性迁移脚本、纯 I/O 包装、`print` 门面 | 可标 **N/A**,但要在 dev-log 写明为何不可测 / 用什么证据替代 |

> pytest 测 Python;测 shell 用 subprocess 而非引入 bats——少一个工具链,`test_vault_sh.py` 已示范。

## RED → GREEN worked example

给 `reportlib.bucket_of` 新增一类(假设要把 `prompts/` 归入「脚本工具」):

**① RED —— 先写会失败的测试**
```python
# tests/test_reportlib.py
def test_bucket_of_prompts():
    assert R.bucket_of("prompts/extract-concepts.md") == "脚本工具"
```
```bash
$ python3 -m pytest tests/test_reportlib.py::test_bucket_of_prompts -q
>       assert R.bucket_of("prompts/extract-concepts.md") == "脚本工具"
E       AssertionError: assert '其它' == '脚本工具'
1 failed          # ← 看到它失败,证明测试确实在测这件事
```

**② GREEN —— 改实现到通过**
```python
# scripts/reportlib.py  _BUCKETS 里
("脚本工具", ("scripts/", "prompts/")),
```
```bash
$ python3 -m pytest tests/test_reportlib.py::test_bucket_of_prompts -q
1 passed
```

**③ REFACTOR —— 清理并跑全量回归**
```bash
$ python3 -m pytest -q      # 全绿才算完,把输出留作证据
```

> 关键:**先看到红**。直接写实现再补一条必过的测试,不算 TDD——那验证不了"测试真的会因缺陷而失败"。

## push 前自动跑(pre-push 钩子)

一次性启用(每个克隆装一次):

```bash
bash scripts/install-hooks.sh    # 设 core.hooksPath → .githooks
```

此后每次 `git push` 前自动跑 `pytest -q`,**红了拦下这次 push**。机制与边界:

- 版本化钩子在 `.githooks/pre-push`,随仓库走(改钩子 = 改仓库文件,可被 `test_pre_push.py` 测)。
- **纯删除分支 / 只推 tag**(git 传入的 local sha 全 0)→ 跳过测试直接放行。
- 无测试(pytest exit 5)、缺 python3 / pytest → 提示但不拦(不因环境缺失挡 push)。
- 临时跳过单次:`git push --no-verify`。
- 注意:检出的分支若**不含** `.githooks`(早于本机制的历史分支),git 会静默跳过钩子——服务端 CI(`.github/workflows/tests.yml`)是这层的兜底,别只依赖本地钩子。

## 现有测试

- `test_reportlib.py` —— `reportlib` 纯函数 characterization(bucket 归类、标记块前缀容错、手记判空、原子写权限等)。
- `test_vault_sh.py` —— `vault.sh repo` 子命令(shell subprocess 测法示范)。
