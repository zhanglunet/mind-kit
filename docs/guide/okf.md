---
title: OKF 合规改造
---

# OKF 合规改造

> 一句话:本库对照 **Open Knowledge Format v0.2** 逐条取证,发现差距只有一条——
> 291 页里有 241 页缺 `type` 字段。补一个键即可,**不必为"合规"重构知识库**。
>
> 可视化版本见文档站的 [OKF 合规](okf.html)页(本文是文字版,内容一致)。

## 0. 四层一图:`okf.py` 站在哪一环

```
来源层        raw/clippings   raw/todo   raw/flomo/delta   raw/pdfs
只读                 │           │             │              │
                     └───────────┴──── 编译 ───┴──────────────┘
                                        ↓                       ← 引擎只读源,不回写
─────────────────────────────────────────────────────────────────────────
引擎层                       sage-wiki compile
sage-wiki 领地      ┌──────────────┬──────────────┬──────────────┐
                    │  summaries/  │  concepts/   │  entities/   │
                    └──────────────┴──────────────┴──────────────┘
                       ↑ 源文件一变,引擎整页重写 → 抹掉注入的键
─────────────────────────────────────────────────────────────────────────
合规层         ①  okf.py --fix     ──▶  ②  build-index.py  ──▶  ③  lint 记账
compile.sh        注入 type              重建 index.md          okf.py --check
流水线            与 stale_after         (读 frontmatter)       freshness
                      ↑                                          decision check
                      └── 自愈:下一轮编译再补回来,幂等,不产生空 diff
                  ↑↑ 顺序不可换:②读的是①写完的 frontmatter
─────────────────────────────────────────────────────────────────────────
消费层        entity_type ──实线──▶ build-index.py:71 · build-wiki-site.py:107
谁在读这些字段  类别        ──实线──▶ build-wiki-site.py:230
              dimension   ──实线──▶ Dataview 看板
              stale_after ──实线──▶ freshness.py(lint 报告)

              type        ┄┄虚线┄┄▶  ✗ 暂无消费者
                                      (OKF 生态工具出现时才兑现)
```

**这张图要说的其实是最后两行。** 前三层是机制,末层是账:`okf.py` 注入的 `type`
**目前全库没有任何程序在读**——`build-index.py` / `build-wiki-site.py` / `indexlib` /
`searchlib` / 三个 Dataview 看板,读的都是 `entity_type`、`类别`、`dimension`、
`decision_type`,没有一个读 `type`。

所以对"要不要补齐"这个问题,诚实的回答是:**补它今天产出为零**;真正划算的是顺带
做成的 `okf.py --check`(引擎领地此前零校验)与 `stale_after` 链路——而那两件
**都不需要 OKF**。留着 `type` 的唯一理由是成本≈0 的互操作期权。
已在 `docs/dev-log.md` 记了 2026-11-03 的复核点:届时仍无消费者就考虑撤回注入。

## 1. Open Knowledge Format 是什么

[OKF](https://github.com/GoogleCloudPlatform/knowledge-catalog/tree/main/okf) 是 Google Cloud
Knowledge Catalog 提出的**中立知识格式**:用 markdown 正文 + YAML frontmatter 表示一条知识,
一个目录就是一个 bundle。它刻意做得薄——**硬性要求只有三条**:

| # | 硬性要求 | 本脚本管不管 |
|---|---|---|
| 1 | 每个非保留 `.md` 有合法 YAML frontmatter | ✅ 管 |
| 2 | 每个 frontmatter 的 `type` 非空 | ✅ 管 |
| 3 | `index.md` / `log.md` 出现时结构符合 §8-9 | ❌ 另议(见第 7 节) |

它还有两条设计约定,恰好是本库能低成本对齐的原因:**保留文件名只有 `index.md` 和 `log.md`
两个**(它们不得有 frontmatter),以及**消费者必须容忍未知键**——这条意味着本库自有的
`entity_type`、`类别`、`decision_type` 全都可以原样留着,不构成不合规。

## 2. 取证:对照下来差多少

先克隆内容库实测,不是读代码猜。291 页知识页:

| 目录 | 页数 | 已有 `type` | 现状字段 |
|---|---|---|---|
| `_wiki/concepts/` | 211 | 0 | `entity_type: concept\|technique\|claim` |
| `_wiki/summaries/` | 8 | 0 | `source` / `source_type` / `compiled_at` |
| `_wiki/outputs/` | 15 | 10 | 部分页已有 |
| `material/` | 35 | 19 | 中文键 `类别` |
| `reports/` | 21 | 21 | 全有(`reportlib` 生成时就写) |
| `_wiki/entities/` | 0 | — | 引擎尚未产出 |
| **合计** | **291** | **50** | **缺 241** |

形态上本库与 OKF 高度重合:bundle 就是目录、`index.md` / `log.md` 早就是保留文件、
未知键本来就到处都是。**结论:不需要改目录、不需要改文件名、不需要动任何现有键。**

这是取证换来的最重要一条。若不取证而按直觉"对齐规范",很容易走成改名重构——
那会砸掉三个现成消费者(见第 4 节)。

## 3. `okf.py`:体检与注入

新增 `scripts/okf.py`,两个互斥模式:

```bash
python3 scripts/okf.py --check    # 只读体检,发现不合规页 → 非零退出
python3 scripts/okf.py --fix      # 幂等注入缺失字段
python3 scripts/okf.py --check --json
```

作用面(bundle 边界)刻意收窄:

```
纳入   _wiki/  material/  reports/
排除   _wiki/under_review/   查询原始产物,确认后才提升入库
       writing/              写作成稿存档,不是知识页
       raw/ browse/ site/ docs/ scripts/
跳过   index.md  log.md      OKF 保留文件,按规范不得有 frontmatter
```

三条设计原则:

- **确定性映射,不用 LLM。** `type` 的值从目录 + 已有键推出,同样输入永远同样输出。
- **幂等。** 已有目标键就一个字节都不写。引擎领地的页每轮编译都会被扫一遍,不幂等的话
  每轮都改文件——git 每天一堆空 diff,还会触发编译引擎的 reconcile churn。
- **只加不改。** 已有 `type` 的页一律不碰(reports 全部、outputs 十来页)。

## 4. `type` 从哪来:确定性映射

目录决定大类,已有键提供更细的值:

| 路径 | `type` | 取值来源 |
|---|---|---|
| `_wiki/concepts/` | `concept` / `technique` / `claim` | **直接搬 `entity_type`**,缺失才回落 `concept` |
| `_wiki/summaries/` | `summary` | 目录 |
| `_wiki/entities/` | `entity` | 目录 |
| `_wiki/outputs/decisions/` | `decision` | 目录(比 `outputs/` 更具体,先判) |
| `_wiki/outputs/` | `output` | 目录 |
| `material/` | `material` | 目录 |
| `reports/` | `report` | 目录 |
| 任意目录下的 `CHANGELOG.md` / `README.md` | `changelog` / `readme` | 文件名(**最先判**) |
| 其余 | `note` | 兜底 |

概念页那一行是关键:`entity_type` 本来就是 OKF 的 `type` 语义,搬过来即可。
注入后的实际分布证明值是真传导了,不是一律拍成 `concept`:

```
143 concept    38 technique    35 material    30 claim
 21 report     14 output        8 summary      1 decision    1 changelog
```

**原键一个不动。** `entity_type` 有两个现成消费者(`build-index.py`、`build-wiki-site.py`),
`类别` 有 Obsidian 属性面板在读,`decision_type` 是决策队列状态机的输入。
OKF 明确要求消费者容忍未知键——所以新增 `type`、老键原样留着,两边都满意;
改名等于**为了合规砸自家管线**。

一页改造前后的样子(只多一行):

```diff
  ---
+ type: concept
  concept: 某个概念
  entity_type: concept
  aliases: ["别名一", "别名二"]
  confidence: medium
  created_at: 2026-07-19T01:47:22Z
  ---
```

**辅助文件的判断必须排在目录判断之前。** 首版把它放在末尾,`material/README.md`
被 `material/` 前缀吃掉、拿到 `type: material`——测试抓到后追到"分支排序"这个根因,
而不是给 README 打特例补丁。

## 5. 接进编译流水线

`compile.sh` 从五步变六步,`okf.py` 占两个位置:

```
1  sage-wiki compile          引擎写出 summaries / concepts / entities
                                        │
2  okf.py --fix        ◀── 注入 ────────┘   必须在这里
                                        │
3  build-index.py            重建 _wiki/index.md(读 frontmatter 生成)
                                        │
4  sage-wiki lint  +  freshness  +  decision check  +  okf.py --check   ◀── 体检记账
                                        │
5  build-wiki-site.py        本地浏览站(best-effort)
                                        │
6  vault.sh commit           写集校验 → 提交编译产物
```

**顺序不是审美。** `index.md` 由 `build-index.py` 读 frontmatter 生成:注入若发生在它之后,
索引拿到的就是上一轮的旧字段。这条已经用测试钉死,免得日后有人调换:

```python
assert i_fix < i_idx, "注入必须在重建 index 之前,否则索引读到旧 frontmatter"
assert i_chk > i_idx, "体检应在 lint 记账阶段(index 之后)"
```

**自愈,不是一次性改造。** 源文件一变,引擎会整页重写、抹掉注入的键——但下一步就是
`--fix`,每轮自动重放。所以别手动补 `type`,跑 `--fix` 就行。

这也是为什么这一步**允许触碰引擎领地**:CLAUDE.md 规定 `_wiki/{summaries,concepts,entities}`
由编译引擎全权负责、人不要手改。`okf.py` 不是"手改",它是流水线的一环,在引擎写完之后
确定性地补齐字段。

## 6. `stale_after`:把保鲜机制接上 OKF

OKF 有个 `stale_after` 键表示"此页何时应视为过期"。本库早就有等价机制(半衰期保鲜),
只是没写成 OKF 的形状——现在把两者接上:

| 声明 | 半衰期 | 适用 |
|---|---|---|
| `volatility: high` | 30 天 | 行业信号、新闻流蒸馏、在办事项的行动清单 |
| `volatility: medium` | 90 天 | 厂商/监管对比、随底层页漂移的综合产物、工具实践 |
| `volatility: low` | 365 天 | 变化很慢的判断 |
| `half_life_days: N` | N 天 | 显式覆盖,优先于 `volatility` |

```
last_confirmed: 2026-07-16          人工确认"此页仍代表现状"的日期
        │
        ├── + 半衰期 30 天 ──▶  stale_after: 2026-08-15    ← okf.py 写回
        │
        └── freshness_factor = 0.5^(距今天数 / 半衰期)
                  ≤ 0.50  → 列入 lint 报告的"值得复核"
                  ≤ 0.25  → 标急
```

**不追踪的页不塞这个键。** 没声明 `volatility` / `half_life_days` 的页面一律不碰,
与既有语义一致:不加字段就不参与追踪。

⚠️ **一条如实的记录**:这套保鲜机制代码早就在、lint 里也跑着,但**上线后很长时间零采用**——
全库没有一页声明过这三个字段,所以 `stale_after` 首次跑出来是 0 页。
后来挑了 5 页真会过时的产出页打标(2 页 high、3 页 medium),链路才真正跑起来。
这是本项目反复撞见的那条:**约束写在文档里等于没有约束**;想让规范被遵守,
就为它写可执行检查。

打标时有两个判断值得记下来:

- **只挑真会过时的页,不搞全量打标。** 复盘类页面记录的是已发生的事,不会过时;
  ingest 摘要是快照式存档;看板由脚本生成。保鲜报表的价值在于短到有人看,
  全量打标等于没打。
- **`last_confirmed` 取写作日期,不是打标当天。** 字段语义是"上次**人工确认**此页仍代表现状",
  没逐条核对过就盖当天,等于伪造一次人工确认,还会把首次复核平白推迟一个半衰期。

## 7. 门禁:引擎领地从零到有

改造之前,写集校验 `validate_write_set.py` 的作用面是:

```python
LLM_SCOPE = ("_wiki/outputs/", "material/", "writing/", "reports/")
```

**`_wiki/summaries/`、`concepts/`、`entities/` 不在里面——引擎领地此前是零门禁**,
引擎写出什么都没人看。`okf.py --check` 补上了最低限度的一道:

| | 改造前 | 改造后 |
|---|---|---|
| 引擎领地校验 | 无 | `okf.py --check`(非零退出) |
| 合规页 / 总页 | 50 / 291 | 291 / 291 |
| 幂等复跑改动 | — | 0 页 |
| `stale_after` 覆盖 | 无此键 | 已声明保鲜的页自动写回 |

验收数据(真实内容库,非合成数据):

```
体检(改造前)  291 页,241 页待补     退出码=1
注入            291 页扫描,241 页更新
体检(改造后)  291 页,0 页待补        退出码=0
幂等第二遍      291 页扫描,0 页更新
写集校验        0 败
```

**没做的部分**:OKF §8-9 规定了 `index.md` / `log.md` 的结构。本库这两个文件各有现成生成器
和现成格式,强行对齐要动生成器、收益不明,留待另议。这是刻意的取舍,不是遗漏。

---

## 相关

- [系统如何运作](architecture.md) —— 三层架构、双库、编译流水线、四道门禁
- [使用手册](usage.md) —— 五大工作流与每周节奏
- [OKF 规范原文](https://github.com/GoogleCloudPlatform/knowledge-catalog/tree/main/okf)
