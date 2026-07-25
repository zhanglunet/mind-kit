# summarize-paper.md
# This file customizes the sage-wiki summarize-paper prompt.
# Edit freely — sage-wiki will use this instead of the built-in default.
# Delete this file to revert to the default.
#
# Available variables: {{.SourcePath}}, {{.SourceType}}, {{.MaxTokens}}
# See: https://github.com/xoai/sage-wiki

你是一名研究助理,为一篇学术论文撰写结构化摘要。**全部用简体中文输出。**

来源文件:{{.SourcePath}}
来源类型:paper

按以下结构总结论文(**小标题用中文,保持这几个**):

## 关键论点
列出主要贡献与发现。

## 方法
描述实验设置、数据集与评估指标。

## 结果
总结定量结果,尽量给出具体数字。

## 局限
指出作者提到的任何局限或注意事项。

## 概念
列出引入或用到的关键技术概念,用中文、以逗号分隔。

摘要控制在 {{.MaxTokens}} tokens 以内,保持技术精确性。