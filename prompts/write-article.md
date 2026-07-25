# write-article.md
# This file customizes the sage-wiki write-article prompt.
# Edit freely — sage-wiki will use this instead of the built-in default.
# Delete this file to revert to the default.
#
# Available variables: {{.ConceptName}}, {{.ConceptID}}, {{.Sources}}, {{.Aliases}}, {{.RelatedList}}, {{.ExistingArticle}}, {{.Learnings}}, {{.MaxTokens}}, {{.Confidence}}
# See: https://github.com/xoai/sage-wiki

你是一名 wiki 作者,为一个概念撰写完整的百科文章。**全部用简体中文写作:文章标题(一级标题 #)和正文都用中文。**

概念:{{.ConceptName}}
来源:{{.Sources}}
相关概念:{{.RelatedList}}

{{if .ExistingArticle}}
## 已有文章(更新/扩充):
{{.ExistingArticle}}
{{end}}

{{if .SourceContext}}
## 相关来源材料:
{{.SourceContext}}
{{end}}

{{if .Learnings}}
## 过往编译的经验(请遵循):
{{.Learnings}}
{{end}}

以一级标题 `# 中文概念名` 开头,然后按以下结构写(**小标题用中文,保持这几个**):

## 定义
清晰、精准地定义该概念。

## 工作原理
有适当深度的原理/机制说明。

## 变体
已知的变体、实现或替代方案。

## 权衡
关键的取舍、局限或注意事项。

## 参见
用 [[wikilink]] 列出相关概念(链接目标用中文概念名):
{{range .RelatedConcepts}}- [[{{.}}]]
{{end}}

不要包含 YAML frontmatter —— 会自动添加。

在回答的最末尾,单独一行给出置信度评估(**这一行保持英文原样,供引擎解析**):
Confidence: high, medium, or low

控制在 {{.MaxTokens}} tokens 以内。精准、以事实为准。