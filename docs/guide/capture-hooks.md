---
title: 静默采集三件套
---

# 静默采集:让知识自己流进来

第二大脑的编译流水线(`sage-wiki compile` → 索引 → 归档)已经是自动的,
真正的摩擦在**第一公里**:好内容产生时,你得想起"这值得存",
再想起"存到 `raw/clippings/`",再手动复制。

静默采集的目标是:**产生内容的那一刻,采集已经发生**。三件套全部汇入
`raw/clippings/`,之后走你熟悉的流程(`sage-wiki compile --watch` 或每周
`bash scripts/compile.sh` + `bash scripts/auto-archive.sh`)。

## 一、剪贴板一键采集

任何地方复制了一段文字,跑:

```bash
python3 scripts/capture-clipboard.py
```

剪贴板内容存为 `raw/clippings/<时间戳>-clipboard-<指纹>.md`,自动带上
`source: clipboard` 的 frontmatter。空剪贴板、与上次重复的内容会自动
跳过(退出码 2),不会产生垃圾条目。

建议绑到全局快捷键(示例):

- macOS:用 Raycast / Alfred / Automator 把这条命令绑到 `⌃⌥C`
- Linux:系统设置 → 键盘 → 自定义快捷键
- Windows:PowerShell 下 `python scripts/capture-clipboard.py`,可用
  AutoHotkey 绑定

## 二、投递目录监听

建一个"你只管丢"的目录,默认 `~/mind-inbox`:

```bash
# 改投递目录(二选一)
export MIND_INBOX=~/Downloads          # 环境变量,或
echo ~/Downloads > .mind-inbox          # 仓库根目录放一行路径
```

启动监听:

```bash
# 常驻(后端自动选: fswatch > inotifywait > 轮询兜底)
bash scripts/capture-watch.sh &

# 或只扫一轮,适合 cron / LaunchAgent / 计划任务
bash scripts/capture-watch.sh --once
```

新丢进来的 `.md` / `.txt` / `.html` 会被**移动**(不是复制)进
`raw/clippings/`,文件名自动加时间戳、清洗非法字符、重名自动加序号。
下载中的临时文件(`.crdownload`、`.part`、点开头)会被跳过;
1 秒内还在变大的文件视为"仍在写入",等下一轮。

macOS 常驻可用 LaunchAgent(仿照 `scripts/com.mind.update-all.plist`
再写一份,把 ProgramArguments 指向本脚本);Windows 用任务计划程序
调 `--once` 每 5 分钟跑一次即可。

## 三、浏览器小书签(一键剪藏)

零安装,任意浏览器可用。新建书签,把下面代码粘贴为网址:

```javascript
javascript:(function(){var t=document.title,u=location.href,s=(window.getSelection()||'').toString().trim()||document.body.innerText.slice(0,8000);var md='---\ntitle: '+t.replace(/\n/g,' ')+'\nsource: '+u+'\ncaptured_at: '+new Date().toISOString()+'\n---\n\n'+s+'\n';var b=new Blob([md],{type:'text/markdown'});var a=document.createElement('a');a.href=URL.createObjectURL(b);a.download=t.replace(/[\\/:*?"<>|]/g,'_').slice(0,60)+'.md';a.click();})();
```

用法:在文章页选中要点(不选则取正文前 8000 字)→ 点书签 →
浏览器下载一个 `.md` 文件 → 把它丢进投递目录(或直接设浏览器下载
目录为投递目录,连"丢"这一步都省了)。

> 隐私说明:小书签全程在本地浏览器里跑,不经过任何服务器;
> 内容只落在你自己的投递目录,凭证不出仓的原则同样适用于采集。

## 三件套如何协同

```
复制文字 ──→ capture-clipboard.py ──┐
随手丢文件 ─→ capture-watch.sh ──────┼──→ raw/clippings/ ──→ sage-wiki compile
浏览器剪藏 ─→ 小书签 → 投递目录 ────┘        (watch / 定时 / 手动)
```

采集只负责"进来",编译、索引、归档仍走原有流水线,互不干扰。
`--dry-run` 可先看效果再真正落盘。
