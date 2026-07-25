# caption-image.md
# This file customizes the sage-wiki caption-image prompt.
# Edit freely — sage-wiki will use this instead of the built-in default.
# Delete this file to revert to the default.
#
# Available variables: {{.SourcePath}}, {{.SourceType}}, {{.MaxTokens}}
# See: https://github.com/xoai/sage-wiki

描述这张来自学术/技术文档的图片。**用简体中文。**

来源:{{.SourcePath}}

给出:
1. 一句话简短说明(caption)
2. 图片是什么(图/示意图/图表/照片)
3. 传达的关键信息

说明控制在 100 字以内。