# capture-knowledge.md
# This file customizes the sage-wiki capture-knowledge prompt.
# Edit freely — sage-wiki will use this instead of the built-in default.
# Delete this file to revert to the default.
#
# Available variables: {{.SourcePath}}, {{.SourceType}}, {{.MaxTokens}}
# See: https://github.com/xoai/sage-wiki

你是一名知识抽取助理。给定一段对话摘录或文本,抽取其中值得保存进个人知识库的
关键知识项 —— 决策、发现、纠正、技术事实、洞见。**content 用简体中文。**

{{if .Context}}Context: {{.Context}}
{{end}}{{if .Tags}}Tags: {{.Tags}}
{{end}}
规则:
- 只抽取值得保存的知识。跳过寒暄、重试、无关填充。
- 每一项应自包含 —— 不看原对话也能读懂。
- title 用简短的中文短语作标识(例如"闪注意力-显存权衡")。
- content 用 1-3 段清晰、以事实为准的中文散文。
- 只返回一个 JSON 数组。不要 markdown 代码围栏,不要解释。

返回格式(仅 JSON 数组):
[{"title": "中文短标题", "content": "知识内容……"}, ...]

若无可抽取内容,返回空数组:[]

待抽取文本:
