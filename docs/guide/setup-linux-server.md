---
title: 在 Linux 服务器上安装与使用(给协作者)
---

# 在 Linux 服务器上安装与使用

> 面向**拿到这个代码库、要在自己 Linux 服务器上从零跑起来**的人。
> 一句话理解这套系统:**代码库(本仓)只有工具,你的知识内容在你自己的另一个私有仓里**——
> 两者用软链接拼成一个工作目录。所以你克隆完会发现没有 `_wiki/`、`material/`,这是**设计如此**,第 3 步会建。

原设计跑在 macOS 桌面(Obsidian + launchd)。本指南给出 Linux 服务器的等价方案,并标出**哪些能力在无头服务器上用不了**。

## 0. 先决条件

| 必需 | 用途 | 装法(Debian/Ubuntu) |
|---|---|---|
| Python ≥ 3.9 | 全部脚本 | `sudo apt install python3 python3-pip` |
| git | 两个仓 | `sudo apt install git` |
| **sage-wiki** | **编译引擎(核心)** | [https://github.com/xoai/sage-wiki](https://github.com/xoai/sage-wiki)(Go,MIT)——按其 README 装;确保在 `PATH` 或 `~/go/bin/` |
| pandoc | 生成文档站(可选) | `sudo apt install pandoc` |
| `markdown` (pip) | 本地浏览站(可选) | 见第 2 步 |

> **没有 sage-wiki 就没有编译能力**——这是外部依赖,本仓不含它。本地检索、写集校验、决策队列、保鲜复核、报表等其余能力不受影响。

## 1. 克隆代码库

```bash
mkdir -p ~/second-brain && cd ~/second-brain
git clone <代码库地址> mind-kit
cd mind-kit
```

**布局很重要**:代码库与内容库必须是**同级目录**(多个脚本按 `../mind-vault` 定位):

```
~/second-brain/
├── mind-kit/     ← 本仓(代码)
└── mind-vault/   ← 你的内容库(第 3 步创建)
```

## 2. 装依赖 + 测试

```bash
pip install -r requirements.txt          # 唯一第三方依赖:markdown(仅本地浏览站用)
pip install -r requirements-dev.txt      # pytest
bash scripts/install-hooks.sh            # 装 pre-push 钩子(push 前自动跑 pytest)
python3 -m pytest -q                     # 应全绿
```

全绿说明工具链就绪(这一步不需要 sage-wiki,也不需要内容)。

## 3. 建你自己的内容库(关键)

```bash
bash scripts/init-vault.sh --dry-run     # 先看计划
bash scripts/init-vault.sh               # 建 ../mind-vault + 软链 + git init
```

它做三件事:① 在 `../mind-vault` 建内容骨架(`_wiki` 四子目录 / `material` 六类 / `raw` 各桶 / `writing` / `reports` 三桶)② 种 `index.md`/`log.md`/`.gitignore` ③ 在代码库里建软链,让 `scripts/vault.sh` 认出双库。

**幂等且不覆盖已有文件**;遇到同名真实目录会跳过并告警,不会销毁你的数据。

验证:

```bash
bash scripts/vault.sh repo    # 必须打印 .../mind-vault
```

> ⚠️ **这一步不能跳过**。若 `_wiki` 软链不存在,`vault.sh` 会**静默退回单库模式**,
> 之后 `vault.sh commit` 会把内容提交到**代码库**而不是你的内容库。

给内容库配一个**私有**远端:

```bash
git -C ../mind-vault remote add origin <你的私有内容仓地址>
bash scripts/vault.sh commit "init: 内容库骨架" && bash scripts/vault.sh push
```

## 4. 配 API Key(GLM / Kimi)

引擎接 OpenAI 兼容的国产编码端点,默认 GLM。**Linux 上多为 bash,写进 `~/.bashrc`(不是 `~/.zshrc`)**:

```bash
echo 'export GLM_API_KEY=...'  >> ~/.bashrc     # 默认后端
echo 'export KIMI_API_KEY=...' >> ~/.bashrc     # 备选后端
source ~/.bashrc
```

| 后端 | env | 端点 | 模型 | 配置 |
|---|---|---|---|---|
| GLM(默认) | `GLM_API_KEY` | `open.bigmodel.cn/api/coding/paas/v4` | `glm-4.5-flash` | `config.glm.yaml` |
| Kimi | `KIMI_API_KEY` | `api.kimi.com/coding/v1` | `kimi-for-coding` | `config.kimi.yaml` |

```bash
bash scripts/sage-backend.sh          # 看当前后端
bash scripts/sage-backend.sh kimi     # 切换
sage-wiki doctor                      # 验证连通
```

> ⚠️ `scripts/compile.sh` 里有一行 `source ~/.zshrc`,bash 环境下它静默跳过。
> 只要 key 已在 `~/.bashrc` 并 `source` 过(或写进 cron 的环境),不影响使用;
> 否则表现为**引擎认证失败**而非明确报错。

## 5. 跑起来

```bash
# 放入素材(网页剪藏 md、PDF、笔记导出)
cp 你的文章.md ../mind-vault/raw/clippings/

bash scripts/compile.sh          # 编译 → 索引 → lint → 保鲜 → 决策校验 → 提交
bash scripts/update-all.sh       # 一键全量:日报 → 编译 → 台账 → 门户 → 文档站
```

`update-all.sh` 缺工具的步骤会自动跳过(比如没装 pandoc 就跳过文档站),不会中断。

**本地查询服务**(提供网页门户与 `/api/search`):

```bash
python3 scripts/brain-server.py          # 默认 127.0.0.1:8788
```

服务器无桌面时,用 SSH 端口转发在本地浏览器打开:

```bash
ssh -L 8788:127.0.0.1:8788 你@服务器      # 然后本地访问 http://127.0.0.1:8788/browse/index.html
```

> 服务只绑回环地址,不对外暴露。**不要**把它绑到 `0.0.0.0`——它能触发本机执行(全量更新)。

## 6. 定时任务:用 cron(不是 launchd)

仓里的 `scripts/com.mind.*.plist` 是 **macOS launchd 专用,Linux 上无效**,忽略它们。等价 cron:

```cron
# 每日 09:30 全量更新
30 9 * * * cd $HOME/second-brain/mind-kit && bash scripts/update-all.sh >> $HOME/.mind-update-all.log 2>&1
# 每日 09:10 日报
10 9 * * * cd $HOME/second-brain/mind-kit && python3 scripts/daily-report.py >> $HOME/.mind-report.log 2>&1
```

cron 环境没有登录 shell 的变量,**必须在 crontab 顶部显式给 key 和 PATH**:

```cron
PATH=/usr/local/bin:/usr/bin:/bin:/home/你/go/bin
GLM_API_KEY=...
```

常驻 `brain-server` 用 systemd user 单元(`~/.config/systemd/user/brain-server.service`):

```ini
[Unit]
Description=mind brain-server
[Service]
ExecStart=/usr/bin/python3 %h/second-brain/mind-kit/scripts/brain-server.py
Restart=always
Environment=GLM_API_KEY=...
[Install]
WantedBy=default.target
```

```bash
systemctl --user enable --now brain-server
loginctl enable-linger $USER      # 让它在你登出后继续跑
```

## 7. 无头服务器上用不了 / 需自行适配的

| 能力 | 状态 | 说明 |
|---|---|---|
| Obsidian + Claudian 侧栏 | ❌ 用不了 | 桌面 GUI。CLI 与网页门户不受影响;可把内容库同步到本地机器再用 Obsidian 打开 |
| `subscriptions.py --notify` | ⚠️ **静默失效** | 用 macOS `osascript` 弹通知;Linux 上**不报错也不弹**。列表与 `--days N` 正常;要通知自行改 `notify-send` 或邮件 |
| `/opt/homebrew/bin` | ✅ 无害 | 几个脚本 PATH 里有它,目录不存在会被忽略 |

## 8. 日常怎么用

- **摄入**:文章丢 `raw/clippings/` → `bash scripts/compile.sh`;重要文章丢 `raw/todo/` 走对话式深度摄入(见《使用手册》)
- **查询**:门户「问一下第二大脑」,或 `sage-wiki query "问题"`
- **健检**:`compile.sh` 已内置 lint + 保鲜复核 + 决策队列校验
- **提交内容**:一律走 `bash scripts/vault.sh commit "说明"`(**不要**在代码库里 `git add` 个人目录——那些路径已 gitignore,`git add` 会静默什么都不做)

更多见 [使用手册](usage.md)、[FAQ 与避坑](faq.md);系统权责边界见仓库根目录 `CLAUDE.md`。

## 9. 更新代码

本仓是线性历史,直接 pull 即可(只更新工具代码,**不碰你的内容库**):

```bash
cd ~/second-brain/mind-kit && git pull
python3 -m pytest -q        # 更新后跑一遍,确认工具链仍正常
```

想自动跟进上游更新,加一条 cron:

```cron
0 8 * * * cd $HOME/second-brain/mind-kit && git pull -q >> $HOME/.mind-kit-pull.log 2>&1
```

## 10. 装完自检

```bash
python3 -m pytest -q                     # 全绿
bash scripts/vault.sh repo               # 打印 .../mind-vault(不是代码库!)
bash scripts/update-all.sh --dry-run     # 看计划,确认哪些步骤会跳过
sage-wiki doctor                         # 引擎连通(装了 sage-wiki 才有)
```

四条都符合预期就算装好了。想理解各部分怎么串起来,看[系统如何运作](architecture.md)。
