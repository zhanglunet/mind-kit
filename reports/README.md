# reports/ — 工作日志(日报 / 周报)

持续记录在知识库上做过的工作,并合成周报。这是 LLM 可写、以脚本自动维护为主的目录,不参与 sage-wiki 编译(已在 `config.yaml` ignore)。

## 结构

- `daily/YYYY-MM-DD.md` — 每日日报,自动盘点当天的 git 提交、`_wiki/log.md` 条目与 flomo 增量
- `weekly/YYYY-Www.md` — 周报,聚合一周日报
- `index.md` — 自动重建的导航索引(纯派生产物,已 gitignore;每次运行脚本时本地重建)

## 生成

```bash
python3 scripts/daily-report.py                # 盘点“昨天”(默认)
python3 scripts/daily-report.py --today        # 今天(截至此刻)
python3 scripts/daily-report.py --days 7        # 回填最近 7 天
python3 scripts/weekly-report.py               # 上一个完整周(周一–周日)
```

## 手记 / 综述区不会被覆盖

日报的“手记”区与周报的“周度综述”区在 `<!-- 手记开始 -->…<!-- 手记结束 -->` /
`<!-- 综述开始 -->…<!-- 综述结束 -->` 标记之间,重新生成时**原样保留**——
放心在里面补写反思、决策复盘、库外工作,或让 LLM 填写叙事。脚本只覆盖标记以上的自动盘点部分。

> ⚠️ 请保留这两行标记本身:只在标记**之间**写内容。删掉“开始”标记会让脚本认不出你写的内容、
> 重生成时用默认留白覆盖它。标记按前缀识别,所以带不带后面的说明文字都行。

## 隐私

日报默认随仓库提交(这是“持续记录”的一部分)。若手记区可能包含敏感内容,
可在 `.gitignore` 加入 `reports/` 或按需排除个别文件。
