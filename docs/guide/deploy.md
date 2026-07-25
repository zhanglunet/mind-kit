---
title: 发布指南
---

# 发布指南:GitHub → Cloudflare Pages

> 发布的是**项目文档站**(`site/` 目录:首页、指南、PRD),不是知识库内容。`raw/`、`_wiki/`、`material/`、`writing/` 永不进入发布目录——知识库本地优先、不做公网分享站,是 PRD §2.2 明确的非目标。

## 发布范围与边界

| 会发布 | 永不发布 |
|---|---|
| `site/`(静态文档站) | `raw/**` 原始来源 |
| — | `_wiki/**` 编译产物 |
| — | `material/**`、`writing/**` |
| — | 任何密钥/配置(API Key 只在环境变量) |

`site/` 为纯静态 HTML(零构建依赖、无外部资源),由 `scripts/build-site.sh` 从 `docs/` 下的 Markdown 生成,手工设计的首页除外。**Markdown 是唯一权威版本**:改文档后重跑构建脚本再提交。

## 方式 A:Cloudflare Pages Git 集成(推荐,零密钥)

1. 把仓库推到 GitHub(私有仓库亦可)。
2. Cloudflare Dashboard → **Workers & Pages → Create → Pages → Connect to Git**,授权并选择本仓库。
3. 构建配置:
   - **Production branch**:`main`
   - **Build command**:留空(纯静态,无需构建)
   - **Build output directory**:`site`
4. Save and Deploy。之后每次 push 到 main,Cloudflare 自动重新部署;Pull Request 会获得预览地址。

## 方式 B:GitHub Actions + Wrangler(备选,需自建工作流)

> 本仓库默认采用方式 A(Git 集成),未内置该工作流。若你偏好用 Actions 自控部署,按下面四步启用。

1. **新增工作流**:在 `.github/workflows/deploy-pages.yml` 写入:

   ```yaml
   name: Deploy docs site to Cloudflare Pages
   on:
     push:
       branches: [main]
       paths: ["site/**", ".github/workflows/deploy-pages.yml"]
     workflow_dispatch:
   jobs:
     deploy:
       runs-on: ubuntu-latest
       permissions:
         contents: read
         deployments: write
       steps:
         - uses: actions/checkout@v4
         - name: Deploy to Cloudflare Pages
           uses: cloudflare/wrangler-action@v3
           with:
             apiToken: ${{ secrets.CLOUDFLARE_API_TOKEN }}
             accountId: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
             command: pages deploy site --project-name=mind-docs
   ```

2. **创建 Pages 项目**(一次性):Dashboard 里 Create → Pages → *Direct Upload*,项目名 `mind-docs`;或本地执行 `npx wrangler pages project create mind-docs`。
3. **创建 API Token**:Cloudflare Dashboard → My Profile → API Tokens → Create Token,使用 *Edit Cloudflare Workers* 模板或自定义授予 **Account – Cloudflare Pages – Edit** 权限。
4. **配置 GitHub Secrets**(仓库 Settings → Secrets and variables → Actions):
   - `CLOUDFLARE_API_TOKEN`:上一步的 token
   - `CLOUDFLARE_ACCOUNT_ID`:Dashboard 首页右侧的 Account ID

之后 push 即部署;也可在 Actions 页手动触发(workflow_dispatch)。Pages 默认地址形如 `https://<项目名>.pages.dev`(占位示例,非本站真实地址);本站已绑定自定义域 **https://aip.cab**(见下方「自定义域名」)。

> ⚠️ 方式 A 与方式 B **二选一**。两者同时启用会对同一 Pages 项目产生重复部署。

## 本地预览与重建

```bash
bash scripts/build-site.sh          # 从 docs/ 重新生成 site/(需要 pandoc)
python3 -m http.server -d site 8000  # 本地预览 http://localhost:8000
```

## 自定义域名

Pages 项目 → Custom domains → 添加你的域名;域名已托管在 Cloudflare 时自动配置 CNAME 与证书。

**本站实际域名:https://aip.cab**（Cloudflare Pages 自定义域,从 `main` 分支的 `site/` 自动部署）。注意 Pages 默认启用 **clean-URL**:访问 `/install.html` 会 307 跳转到 `/install`——用 `curl` 验证内容时要加 `-L` 跟随重定向。

## 发布前安全清单

- [ ] `site/` 内没有任何来自 `raw/`、`_wiki/`、`material/`、`writing/` 的内容
- [ ] 没有 API Key、token、私有路径出现在任何页面(`grep -r "sk-" site/` 应为空)
- [ ] PRD 页为最新导出(修订 `.md` 后已重跑 `build-site.sh`)
