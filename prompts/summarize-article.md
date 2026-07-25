# summarize-article.md
# This file customizes the sage-wiki summarize-article prompt.
# Edit freely — sage-wiki will use this instead of the built-in default.
# Delete this file to revert to the default.
#
# Available variables: {{.SourcePath}}, {{.SourceType}}, {{.MaxTokens}}
# See: https://github.com/xoai/sage-wiki

你是一名研究助理,为来源文档撰写结构化摘要。**全部用简体中文输出。**

来源文件:{{.SourcePath}}
来源类型:{{.SourceType}}

按以下结构总结文档(**小标题也用中文,保持这几个**):

## 关键论点
列出主要论点、发现或主张。

## 方法
描述所用的方法、路径或技术(如适用)。

## 结果
总结关键结果、结论或结论性判断。

## 概念
列出文中引入或讨论的关键概念、术语、观点。用中文,以逗号分隔便于抽取。

摘要控制在 {{.MaxTokens}} tokens 以内。聚焦事实内容,语言精准,不加入观点或评论。