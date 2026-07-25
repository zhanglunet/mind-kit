# scripts/reportlib.py
# 日报/周报共用工具:从 git 提交与 _wiki/log.md 盘点某一天的工作。
# 被 daily-report.py 与 weekly-report.py 导入(两者用 sys.path 把 scripts/ 加入路径)。
# 需要 Python 3.9+。设计原则:每条结论可回溯到具体 git sha 或 log.md 条目。
import os, re, subprocess, tempfile
from pathlib import Path
from datetime import date, datetime, timedelta

VAULT = Path(__file__).resolve().parent.parent
LOG = VAULT / "_wiki" / "log.md"
FLOMO_DELTA = VAULT / "raw" / "flomo" / "delta"
REPORTS = VAULT / "reports"
DAILY = REPORTS / "daily"
WEEKLY = REPORTS / "weekly"

# 手记/综述区标记:与全部文档示例保持一致的“短式”;匹配时按前缀容错(见 preserve_block),
# 所以文档里手写 `<!-- 手记开始 -->` 或带说明的长式都能被正确识别与保留。
HAND_BEGIN = "<!-- 手记开始 -->"
HAND_END = "<!-- 手记结束 -->"
LLM_BEGIN = "<!-- 综述开始 -->"
LLM_END = "<!-- 综述结束 -->"

# 手记默认留白:HAND_BODY 作为新日报的默认块;HAND_PLACEHOLDER 用于判空(未改动即视为空)
HAND_PLACEHOLDER = "（留白:今日反思、决策复盘、库外工作 —— 由你或 LLM 补写。）"
HAND_BODY = f"## 手记\n\n{HAND_PLACEHOLDER}"

WEEKDAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

# git 提交按顶层路径归类;顺序即展示顺序,匹配到的第一类生效
_BUCKETS = [
    ("摄入与编译", ("raw/", "_wiki/summaries", "_wiki/concepts", "_wiki/entities")),
    ("查询产出", ("_wiki/outputs",)),
    ("写作素材", ("material/", "writing/")),
    ("报告", ("reports/",)),
    ("脚本工具", ("scripts/",)),
    ("文档站点", ("docs/", "site/", "README.md", "CLAUDE.md", "CHANGELOG.md")),
    ("配置", ("config.", ".mcp.json", ".gitignore", ".github/")),
]
_LOG_RE = re.compile(r"^##\s*\[(\d{4}-\d{2}-\d{2})\]\s*(\S+)\s*[｜|]\s*(.+?)\s*$")
_NOTE_COUNT_RE = re.compile(r"共\s*(\d+)\s*条新笔记")
# 归类时忽略的“非工作”占位文件(骨架 .gitkeep 不代表当天做了工作)
_IGNORE_BASENAMES = {".gitkeep", ".gitignore"}

_COMMIT_CACHE = None  # {day: [{sha, subject, files, buckets}]},每进程构建一次


def _git(args, repo=None):
    """运行 git 命令(默认在代码库 VAULT;可指定内容库),失败时抛出带 stderr 的异常。"""
    r = subprocess.run(["git", "-C", str(repo or VAULT), *args],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} 失败:{r.stderr.strip()}")
    return r.stdout


def _has_head(repo=None) -> bool:
    """仓库是否已有至少一个提交(空仓库/新克隆未提交时为 False)。"""
    return subprocess.run(["git", "-C", str(repo or VAULT), "rev-parse", "--verify", "-q", "HEAD"],
                          capture_output=True, text=True).returncode == 0


def _toplevel(path) -> "str | None":
    r = subprocess.run(["git", "-C", str(path), "rev-parse", "--show-toplevel"],
                       capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def _repos() -> "list[str]":
    """要盘点提交的 git 库:代码库 +(若个人目录软链到独立的 mind-vault)内容库。
    单库(未拆分)时两者相同,只返回一个,行为与拆库前一致。"""
    repos = []
    code = _toplevel(VAULT)
    if code:
        repos.append(code)
    wiki = VAULT / "_wiki"
    if wiki.exists():
        content = _toplevel(wiki)
        if content and content not in repos:
            repos.append(content)
    return repos or [str(VAULT)]


def safe_read(path: Path):
    """严格 UTF-8 读取;非 UTF-8 时告警并返回 None(不静默丢字、不崩溃),与 flomo-delta.py 策略一致。"""
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as e:
        print(f"⚠ 警告:{path} 不是 UTF-8 编码({e.reason}),本次已跳过。"
              f"请转码后重试(如 iconv -f GBK -t UTF-8)。")
        return None


def bucket_of(path: str) -> str:
    for name, prefixes in _BUCKETS:
        if any(path == p or path.startswith(p) for p in prefixes):
            return name
    return "其它"


def _build_commit_cache() -> dict:
    """一次性把全部提交按作者日期(本地时区)分组;过滤 .gitkeep 等占位文件。
    拆库后同时盘点代码库与内容库(mind-vault)的提交;单库时只有一个库,行为不变。"""
    cache = {}
    for repo in _repos():
        if not _has_head(repo):
            continue
        out = _git(["log", "--no-merges", "--date=format-local:%Y-%m-%d",
                    "--pretty=%h%x1f%ad%x1f%s"], repo=repo)
        for line in out.splitlines():
            if not line.strip():
                continue
            sha, adate, subject = line.split("\x1f", 2)
            files = [f for f in _git(
                ["-c", "core.quotepath=false",
                 "diff-tree", "--no-commit-id", "--name-only", "-r", "--root", sha],
                repo=repo
            ).splitlines()
                if f.strip() and os.path.basename(f) not in _IGNORE_BASENAMES]
            buckets = {}
            for f in files:
                buckets.setdefault(bucket_of(f), []).append(f)
            cache.setdefault(adate, []).append(
                {"sha": sha, "subject": subject, "files": files, "buckets": buckets})
    return cache


def commits_on(day: str) -> "list[dict]":
    """作者日期(本地时区)为 day 的提交。空仓库返回 [],不崩溃。"""
    global _COMMIT_CACHE
    if _COMMIT_CACHE is None:
        _COMMIT_CACHE = _build_commit_cache()
    return _COMMIT_CACHE.get(day, [])


def log_entries_on(day: str) -> "list[dict]":
    """解析 _wiki/log.md 中日期为 day 的条目:[{type, title}]。非 UTF-8 时告警跳过。"""
    if not LOG.exists():
        return []
    text = safe_read(LOG)
    if text is None:
        return []
    entries = []
    for line in text.splitlines():
        m = _LOG_RE.match(line)
        if m and m.group(1) == day:
            entries.append({"type": m.group(2), "title": m.group(3)})
    return entries


def flomo_deltas_on(day: str) -> "list[dict]":
    """当天生成的 flomo delta 文件:[{name, count}]。非 UTF-8 时告警跳过该文件。"""
    if not FLOMO_DELTA.is_dir():
        return []
    out = []
    for p in sorted(FLOMO_DELTA.glob(f"delta-{day}*.md")):
        text = safe_read(p)
        if text is None:
            continue
        m = _NOTE_COUNT_RE.search(text)
        out.append({"name": p.name, "count": int(m.group(1)) if m else None})
    return out


def gather(day: str) -> dict:
    """盘点某一天的全部工作,汇总为一个字典(供渲染)。"""
    commits = commits_on(day)
    logs = log_entries_on(day)
    deltas = flomo_deltas_on(day)
    counts = {t: sum(1 for e in logs if e["type"] == t)
              for t in ("ingest", "query", "lint")}
    touched = {}  # 类别 -> 去重文件数
    for c in commits:
        for cat, fs in c["buckets"].items():
            touched.setdefault(cat, set()).update(fs)
    return {
        "commits": commits,
        "logs": logs,
        "deltas": deltas,
        "ingest": counts["ingest"],
        "query": counts["query"],
        "lint": counts["lint"],
        "flomo_notes": sum(d["count"] or 0 for d in deltas),
        "touched": {k: len(v) for k, v in touched.items()},
        "has_activity": bool(commits or logs or deltas),
    }


def weekday_cn(day: str) -> str:
    return WEEKDAY_CN[datetime.strptime(day, "%Y-%m-%d").weekday()]


def frontmatter(title: str, **fields) -> "list[str]":
    """生成报告的 YAML frontmatter 行列表(type 固定为 report)。"""
    lines = ["---", f"title: {title}", "type: report"]
    lines += [f"{k}: {v}" for k, v in fields.items()]
    lines += ["---", ""]
    return lines


def recent_days(n: int) -> "list[str]":
    """最近 n 天(含昨天),升序返回 ISO 日期串。n=1 即“昨天”。"""
    yst = date.today() - timedelta(days=1)
    return [(yst - timedelta(days=i)).isoformat() for i in range(n - 1, -1, -1)]


def find_block(text: str, begin: str, end: str):
    """在 text 中按前缀定位标记块。begin 只需匹配其起始(容忍长式/短式差异)。
    返回 (start_idx, end_idx_exclusive, body) 或 None。end 缺失时延伸到文末。"""
    prefix = begin.split("-->")[0]  # 如 "<!-- 手记开始 " → 对长短式都成立
    i = text.find(prefix)
    if i == -1:
        return None
    # 从 begin 行结束处取正文
    line_end = text.find("\n", i)
    body_start = line_end + 1 if line_end != -1 else len(text)
    j = text.find(end, body_start)
    if j == -1:
        return (i, len(text), text[body_start:].rstrip())
    return (i, j + len(end), text[body_start:j].rstrip())


def preserve_block(path: Path, begin: str, end: str, default_body: str) -> str:
    """若 path 已存在且含 begin 标记,原样保留其整块;否则返回默认块。
    标记按前缀匹配,文档里的短式与代码里的写法都能识别(见 §7.7 / reports/README)。"""
    if path.exists():
        text = safe_read(path)
        if text is not None:
            found = find_block(text, begin, end)
            if found:
                return text[found[0]:found[1]]
    return f"{begin}\n{default_body}\n{end}"


def extract_hand(path: Path) -> str:
    """抽取某日报手记区正文;恰为默认留白则视为空(精确比较,不误伤以“（留白”开头的真实手记)。"""
    if not path.exists():
        return ""
    text = safe_read(path)
    if text is None:
        return ""
    found = find_block(text, HAND_BEGIN, HAND_END)
    if not found:
        return ""
    body = re.sub(r"^\s*##\s*手记\s*\n", "", found[2], count=1).strip()  # 只去开头一个“## 手记”标题
    return "" if body == HAND_PLACEHOLDER else body


def atomic_write(path: Path, text: str) -> None:
    """临时文件 + os.replace 原子写入;权限对齐仓库常规 0644(mkstemp 默认 0600)。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fp:
            fp.write(text)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _first_overview(path: Path) -> str:
    """从报告的“概览/本周概览”区抓第一条要点作为索引摘要。"""
    text = safe_read(path)
    if text is None:
        return ""
    in_ov = False
    for ln in text.splitlines():
        if ln.startswith("## 概览") or ln.startswith("## 本周概览"):
            in_ov = True
            continue
        if in_ov and ln.strip().startswith("-"):
            return ln.strip().lstrip("-").strip()
        if in_ov and ln.startswith("## "):
            break
    return ""


def _sort_key(stem: str) -> str:
    """报告文件名 → 可比较的日期键(用于索引“最新在前”)。
    日报 YYYY-MM-DD / 周报 ISO YYYY-Www / 周报区间 YYYY-MM-DD_YYYY-MM-DD 都归一到日期。"""
    m = re.fullmatch(r"(\d{4})-W(\d{2})", stem)
    if m:
        try:
            return date.fromisocalendar(int(m.group(1)), int(m.group(2)), 1).isoformat()
        except ValueError:
            return stem
    m = re.match(r"(\d{4}-\d{2}-\d{2})", stem)
    return m.group(1) if m else stem


def rebuild_index() -> None:
    """扫描 reports/daily 与 reports/weekly,重建 reports/index.md 导航表(最新在前)。"""
    lines = ["# 报告索引", "",
             "> 由 daily-report.py / weekly-report.py 自动重建(纯派生,已 gitignore)。日报见 `daily/`,周报见 `weekly/`。", ""]
    weeks = sorted(WEEKLY.glob("*.md"), key=lambda p: _sort_key(p.stem), reverse=True) if WEEKLY.is_dir() else []
    if weeks:
        lines += ["## 周报", "", "| 周 | 概览 |", "|---|---|"]
        lines += [f"| [{p.stem}](weekly/{p.name}) | {_first_overview(p)} |" for p in weeks]
        lines.append("")
    days = sorted(DAILY.glob("20*.md"), key=lambda p: _sort_key(p.stem), reverse=True) if DAILY.is_dir() else []
    if days:
        lines += ["## 日报", "", "| 日期 | 概览 |", "|---|---|"]
        lines += [f"| [{p.stem}](daily/{p.name}) | {_first_overview(p)} |" for p in days]
        lines.append("")
    if not weeks and not days:
        lines.append("*(尚无报告 —— 运行 `python3 scripts/daily-report.py` 生成第一份)*")
    atomic_write(REPORTS / "index.md", "\n".join(lines) + "\n")
