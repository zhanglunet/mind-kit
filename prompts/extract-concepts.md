# extract-concepts.md
# This file customizes the sage-wiki extract-concepts prompt.
# Edit freely — sage-wiki will use this instead of the built-in default.
# Delete this file to revert to the default.
#
# Available variables: {{.ExistingConcepts}}, {{.Summaries}}
# See: https://github.com/xoai/sage-wiki

你是一个中文知识库的概念抽取系统。**全部用简体中文输出。**

根据下面这些"新增/更新来源"的摘要,抽取其中值得单独成页的概念。

**粒度要求(重要):追求细粒度、宁多勿少。** 除了顶层的宽概念,也要把重要的**技术、方法、框架、架构组件、子概念、关键主张**分别抽成独立条目;只要一个说法值得读者单独查阅,就单列。不要为了"精炼"把多个不同侧面塞进一个大概念。一篇有实质内容的来源通常能抽出 10 个以上概念。

## 已有概念(不要重复):
{{.ExistingConcepts}}

## 新增/更新的摘要:
{{.Summaries}}

对每个概念,给出:
- name: 简洁的**中文**概念名(例如"自注意力机制""湖仓一体架构")。不要用英文、不要用连字符 slug;广为人知的专有名词/缩写可保留原文(如 MCP、Transformer、A2A)。
- aliases: 别名(中文优先,可含原文缩写)
- sources: 提到该概念的来源文件
- type: 从 concept / technique / claim 三者中选(**此字段保持英文枚举**,是分类标签)

只有当两者**确为同一事物的不同叫法**时才合并(如"湖仓一体"="Lakehouse");不同侧面、子概念、具体技术应各自独立,**不要过度合并**。
只输出一个 JSON 数组(对象组成)。不要 markdown,不要解释。