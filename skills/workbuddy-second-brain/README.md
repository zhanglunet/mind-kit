# 第二大脑 WorkBuddy 技能包

这是一个供 WorkBuddy 用户导入的个人技能包。

## 包含内容

- `skill.yaml`：技能元数据和隐私声明。
- `SKILL.md`：安装、编译、安全边界，以及两种发行包的区分。

## 它能做什么

- **公开仓 mind-kit（人人可装）**：指导安装 **Vault-only** 安装器，初始化本地知识库并首次编译。
  公开包**不含飞书同步连接器**，不能执行飞书授权或内容同步。
- **完整发行包（邀请制内测）**：同一个安装器会显示飞书授权页，技能另行指导最小权限申请、
  本人授权与增量同步。申请见 <https://aip.cab/services>。

## 安全声明

本包不包含任何 App Secret、Token、个人飞书内容、仓库凭证或本地路径。技能只在用户明确确认后
指导本机执行安装器；飞书授权（若适用）始终由用户本人完成。

本包是个人可导入技能，不代表 WorkBuddy 官方技能市场或专家市场已经审核上架。

## 官方说明

- 使用指南：<https://aip.cab/workbuddy>
- 公开安装仓库：<https://github.com/zhanglunet/mind-kit>

## 本包怎么来的

包内文件的权威版本是源仓库的 `skills/workbuddy-second-brain/`，zip 由
`scripts/build-skill-package.py` 确定性构建（同源必同字节），并有 pytest 门禁锁定
「产物与源一致」。不要手工解包修改后再打包——那样改动无法被 review，也无法被检查发现。
