#!/bin/bash
# scripts/build-site.sh —— 从 Markdown 重建文档站 site/
# 权威版本永远是 Markdown:docs/guide/*.md、CHANGELOG.md、docs/prd/*.md。
# 需要 pandoc;首页 site/index.html 为手工设计,本脚本不改动它。
set -euo pipefail

# 解释器解析:系统 python3 可能是 EOL 的 3.6(真机实测),依赖在 .venv 里。
. "$(dirname "${BASH_SOURCE[0]}")/_pyresolve.sh"
MIND_PY="$(mind_python "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)")"


VAULT="$(cd "$(dirname "$0")/.." && pwd)"
SITE="$VAULT/site"
TPL="$VAULT/scripts/site-template.html"

command -v pandoc >/dev/null || { echo "错误:需要 pandoc(brew install pandoc / apt install pandoc)" >&2; exit 1; }
mkdir -p "$SITE"

wrap_tables() {  # 给宽表格加横向滚动容器
  "$MIND_PY" - "$1" <<'EOF'
import sys
p = sys.argv[1]
s = open(p, encoding='utf-8').read()
s = s.replace('<table>', '<div class="table-wrap">\n<table>').replace('</table>', '</table>\n</div>')
open(p, 'w', encoding='utf-8').write(s)
EOF
}

build_page() {  # build_page <md 文件> <输出名> <导航高亮变量>
  local md="$1" out="$2" active="$3"
  pandoc "$md" -f markdown -t html --template "$TPL" --toc --toc-depth=2 \
    -V "active_${active}=1" -o "$SITE/$out"
  wrap_tables "$SITE/$out"
  echo "  ✓ site/$out"
}

echo "重建文档站:"
build_page "$VAULT/docs/guide/install.md"  install.html   install
build_page "$VAULT/docs/guide/usage.md"    usage.html     usage
build_page "$VAULT/docs/guide/faq.md"      faq.html       faq
build_page "$VAULT/docs/guide/deploy.md"   deploy.html    deploy
build_page "$VAULT/docs/guide/setup-linux-server.md" server.html server
build_page "$VAULT/docs/guide/quick-install.md" quick-install.html quick_install
build_page "$VAULT/docs/guide/agent-install.md" agent-install.html agent_install
build_page "$VAULT/docs/guide/workbuddy.md" workbuddy.html workbuddy
build_page "$VAULT/docs/guide/services.md"  services.html  services
# 标题走 --metadata-file 而非 --metadata CLI 参数:argv 按 **locale** 解码,
# 在 C/POSIX locale 的机器上(VM 的 cron 就是)中文标题每个字节变成 U+FFFD
# 烧进 HTML(真机实测:title 与面包屑双双乱码);metadata 文件 pandoc 恒按
# UTF-8 读,与机器 locale 无关。
META_DIR="$(mktemp -d)"
trap 'rm -rf "$META_DIR"' EXIT
printf 'title: 更新日志\n' > "$META_DIR/changelog.yaml"
printf 'title: 产品需求文档(PRD)\n' > "$META_DIR/prd.yaml"

pandoc "$VAULT/CHANGELOG.md" -f markdown -t html --template "$TPL" --toc --toc-depth=2 \
  --metadata-file "$META_DIR/changelog.yaml" -V active_changelog=1 -o "$SITE/changelog.html"
wrap_tables "$SITE/changelog.html"
echo "  ✓ site/changelog.html"

# PRD:从权威 Markdown 直接 pandoc 渲染(不再依赖手工"精装"导出;与指南页同一模板、始终跟源同步)
# PRD.md 无 title frontmatter,故走 metadata 文件(同 changelog,防 argv 按 locale 解码出乱码)
pandoc "$VAULT/docs/prd/第二大脑-个人知识库-PRD.md" -f markdown -t html --template "$TPL" --toc --toc-depth=2 \
  --metadata-file "$META_DIR/prd.yaml" -V active_prd=1 -o "$SITE/prd.html"
wrap_tables "$SITE/prd.html"
echo "  ✓ site/prd.html(pandoc 从 PRD.md 渲染)"

# 指南 Markdown 内的 .md 互链改为 .html
# 规则:同名 .html 存在就改写(手工页如 architecture.html 也算),否则原样留着——
# 由 tests/test_site_docs.py 的死链门禁把漏网的揪出来,不靠这里维护一份易过期的白名单。
"$MIND_PY" - "$SITE" <<'EOF'
import re, sys, pathlib
site = pathlib.Path(sys.argv[1])
RENAME = {'setup-linux-server.md': 'server.html'}   # 文件名与页面名不一致的特例

def to_html(m):
    out = RENAME.get(m.group(1), m.group(1)[:-3] + '.html')
    return f'href="{out}"' if (site / out).exists() else m.group(0)

for p in site.glob('*.html'):
    s = p.read_text(encoding='utf-8')
    s2 = re.sub(r'href="([A-Za-z0-9_.-]+\.md)"', to_html, s)
    if s2 != s:
        p.write_text(s2, encoding='utf-8')
EOF

echo "完成。本地预览:python3 -m http.server -d site 8000"
