#!/usr/bin/env python3
"""第二大脑本地安装与飞书授权向导。

安全边界：
- Web 服务只监听 127.0.0.1，并要求每次请求携带随机会话令牌；
- App Secret 只通过 stdin 交给 lark-cli，不写日志或仓库；
- verification_url / device_code 仅保存在当前进程内存，完成或失败即清除；
- 飞书 token 由 lark-cli 写入系统钥匙串，本程序不读取、不保存。
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable, Iterable
from urllib.parse import parse_qs, urlparse

import larklib
import vault_init


ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
OFFICIAL_PERMISSION_DOC = (
    "https://open.feishu.cn/document/server-docs/application-scope/"
    "introduction?lang=zh-CN"
)
FEISHU_DEVELOPER_CONSOLE = "https://open.feishu.cn/app"

CORE_SCOPES = (
    "drive:drive:readonly",
    "docx:document:readonly",
    "wiki:wiki:readonly",
)
FILE_SCOPES = ("search:docs:read", "drive:file:download")
MESSAGE_SCOPES = (
    "im:chat:read",
    "im:message.group_msg:get_as_user",
    "im:message.p2p_msg:get_as_user",
)

PROFILE_RE = re.compile(r"^[A-Za-z0-9._-]{1,48}$")
APP_ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,128}$")
SECRET_PATTERNS = (
    re.compile(r'(?i)(app[_ -]?secret|access[_ -]?token|refresh[_ -]?token)(["\s:=]+)([^\s",}]+)'),
    re.compile(r'(?i)(device[_ -]?code)(["\s:=]+)([^\s",}]+)'),
)


def redact(text: str) -> str:
    """Best-effort log redaction; secrets are never intentionally logged."""
    out = text
    for pattern in SECRET_PATTERNS:
        out = pattern.sub(r"\1\2[REDACTED]", out)
    return out


def selected_scopes(include_files: bool, include_messages: bool) -> tuple[str, ...]:
    scopes = list(CORE_SCOPES)
    if include_files:
        scopes.extend(FILE_SCOPES)
    if include_messages:
        scopes.extend(MESSAGE_SCOPES)
    return tuple(scopes)


def module_available(name: str) -> bool:
    required = {
        "files": SCRIPTS / "feishu-backup-files.py",
        "messages": SCRIPTS / "feishu-backup-messages.py",
    }
    return required[name].is_file()


def venv_python(root: Path = ROOT, platform: str | None = None) -> Path:
    """Return the platform-native virtualenv interpreter path."""
    platform = platform or os.name
    return root / ".venv" / ("Scripts/python.exe" if platform == "nt" else "bin/python")


def sync_plan(python: str, include_files: bool, include_messages: bool) -> list[tuple[str, list[str]]]:
    """Return an argv-only plan. Every source first gets a small smoke run."""
    plan: list[tuple[str, list[str]]] = [
        ("检查冷存写权限", [python, "scripts/feishu_preflight.py"]),
        ("云文档冒烟（3 篇）", [python, "scripts/feishu-backup-docs.py", "--limit", "3"]),
        ("知识库规模检查", [python, "scripts/feishu-backup-wiki.py", "--count-only"]),
        ("同步我拥有的云文档", [python, "scripts/feishu-backup-docs.py"]),
        ("同步知识库文档", [python, "scripts/feishu-backup-wiki.py"]),
    ]
    if include_files:
        plan.extend(
            [
                ("云盘文件冒烟（3 个）", [python, "scripts/feishu-backup-files.py", "--limit", "3"]),
                ("同步我拥有的云盘文件", [python, "scripts/feishu-backup-files.py"]),
            ]
        )
    if include_messages:
        plan.extend(
            [
                (
                    "聊天记录冒烟（3 个会话）",
                    [python, "scripts/feishu-backup-messages.py", "--types", "group,p2p", "--limit", "3"],
                ),
                (
                    "同步群聊和单聊",
                    [python, "scripts/feishu-backup-messages.py", "--types", "group,p2p"],
                ),
            ]
        )
    return plan


def parse_json_envelope(proc: subprocess.CompletedProcess[str]) -> dict:
    for raw in (proc.stdout, proc.stderr):
        raw = (raw or "").strip()
        if not raw:
            continue
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise RuntimeError(redact(f"lark-cli 未返回 JSON：{proc.stdout[:200]} {proc.stderr[:200]}"))


def find_first(value, keys: Iterable[str]):
    if isinstance(value, dict):
        for key in keys:
            if value.get(key):
                return value[key]
        for child in value.values():
            found = find_first(child, keys)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = find_first(child, keys)
            if found:
                return found
    return None


Runner = Callable[..., subprocess.CompletedProcess[str]]


def default_runner(argv, **kwargs):
    return subprocess.run(argv, **kwargs)


@dataclass
class WizardState:
    profile: str = "second-brain"
    phase: str = "ready"
    message: str = "请先在飞书开放平台创建企业自建应用并开通所列权限。"
    include_files: bool = False
    include_messages: bool = False
    verification_url: str | None = None
    device_code: str | None = None
    qr_png: bytes | None = None
    logs: list[str] = field(default_factory=list)
    sync_started: bool = False
    lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

    def add_log(self, line: str):
        with self.lock:
            self.logs.append(redact(line.rstrip()))
            self.logs[:] = self.logs[-500:]

    def public(self) -> dict:
        with self.lock:
            return {
                "phase": self.phase,
                "message": self.message,
                "profile": self.profile,
                "include_files": self.include_files,
                "include_messages": self.include_messages,
                "verification_url": self.verification_url,
                "has_qr": self.qr_png is not None,
                "logs": list(self.logs),
                "sync_started": self.sync_started,
            }

    def clear_device_flow(self):
        with self.lock:
            self.device_code = None
            self.verification_url = None
            self.qr_png = None


class Installer:
    def __init__(self, state: WizardState, runner: Runner = default_runner):
        self.state = state
        self.runner = runner
        self.runtime = tempfile.TemporaryDirectory(prefix="mind-auth-")

    @property
    def python(self) -> str:
        candidate = venv_python(ROOT)
        return str(candidate if candidate.exists() else Path(sys.executable))

    def _env(self) -> dict[str, str]:
        env = os.environ.copy()
        env["LARKSUITE_CLI_NO_UPDATE_NOTIFIER"] = "1"
        env["LARKSUITE_CLI_NO_SKILLS_NOTIFIER"] = "1"
        env["MIND_LARK_PROFILE"] = self.state.profile
        return env

    def _run(self, argv: list[str], *, stdin: str | None = None, timeout: int = 300):
        return self.runner(
            argv,
            cwd=str(ROOT),
            env=self._env(),
            input=stdin,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def configure(self, app_id: str, app_secret: str, profile: str):
        if not APP_ID_RE.fullmatch(app_id):
            raise ValueError("App ID 格式不正确。")
        if not app_secret or len(app_secret) > 512:
            raise ValueError("请填写 App Secret。")
        if not PROFILE_RE.fullmatch(profile):
            raise ValueError("Profile 只能包含字母、数字、点、下划线和连字符。")

        argv = larklib.lark_argv([
            "config", "init", "--app-id", app_id,
            "--app-secret-stdin", "--brand", "feishu", "--name", profile,
        ], profile="")
        if os.environ.get("OPENCLAW_HOME") or os.environ.get("HERMES_HOME"):
            # 用户明确要求给第二大脑配置独立飞书应用；Agent 环境下需显式允许。
            argv.append("--force-init")
        proc = self._run(argv, stdin=app_secret + "\n")
        app_secret = ""  # 尽早释放引用；不写 state / 日志 / 文件。
        if proc.returncode != 0:
            raise RuntimeError(redact(proc.stderr or proc.stdout or "lark-cli 配置失败"))
        with self.state.lock:
            self.state.profile = profile
            self.state.phase = "configured"
            self.state.message = "本机应用配置完成，可以发起用户授权。"
        self.state.add_log(f"✓ lark-cli profile 已配置：{profile}")

    def start_authorization(self, include_files: bool, include_messages: bool):
        if include_files and not module_available("files"):
            raise RuntimeError("当前发行包不含云盘文件同步模块。")
        if include_messages and not module_available("messages"):
            raise RuntimeError("当前发行包不含聊天记录同步模块。")
        scopes = selected_scopes(include_files, include_messages)
        with self.state.lock:
            self.state.include_files = include_files
            self.state.include_messages = include_messages
        argv = larklib.lark_argv(
            ["auth", "login", "--scope", " ".join(scopes), "--no-wait", "--json"],
            profile=self.state.profile,
        )
        proc = self._run(argv)
        envelope = parse_json_envelope(proc)
        if proc.returncode != 0 or envelope.get("ok") is not True:
            error = envelope.get("error") or {}
            console_url = error.get("console_url")
            msg = error.get("message") or proc.stderr or "无法发起授权"
            if console_url:
                msg += f"\n请先在飞书开发者后台开通权限：{console_url}"
            raise RuntimeError(redact(msg))

        url = find_first(envelope, ("verification_url", "verification_uri_complete", "verification_uri"))
        code = find_first(envelope, ("device_code", "deviceCode"))
        if not url or not code:
            raise RuntimeError("授权响应缺少 verification_url 或 device_code。")

        qr_name = "feishu-auth-qrcode.png"
        qr_proc = self.runner(
            larklib.lark_argv(["auth", "qrcode", str(url), "--output", qr_name, "--size", "320"], profile=""),
            cwd=self.runtime.name,
            env=self._env(),
            capture_output=True,
            text=True,
            timeout=60,
        )
        if qr_proc.returncode != 0:
            raise RuntimeError(redact(qr_proc.stderr or "二维码生成失败"))
        qr_bytes = (Path(self.runtime.name) / qr_name).read_bytes()
        with self.state.lock:
            self.state.device_code = str(code)
            self.state.verification_url = str(url)  # opaque string，不改写。
            self.state.qr_png = qr_bytes
            self.state.phase = "authorizing"
            self.state.message = "请打开授权链接或扫描二维码；完成后点击“授权完成并开始同步”。"
        self.state.add_log(f"✓ 已发起最小权限授权（{len(scopes)} 项）")

    def complete_authorization_and_sync(self):
        with self.state.lock:
            code = self.state.device_code
            if not code:
                raise RuntimeError("授权会话不存在或已过期，请重新发起授权。")
            self.state.phase = "verifying"
            self.state.message = "正在确认授权……"
        proc = self._run(
            larklib.lark_argv(["auth", "login", "--device-code", code, "--json"], profile=self.state.profile),
            timeout=180,
        )
        # 无论成败都不保留 device_code / URL / QR。
        self.state.clear_device_flow()
        envelope = parse_json_envelope(proc)
        if proc.returncode != 0 or envelope.get("ok") is not True:
            with self.state.lock:
                self.state.phase = "auth_failed"
                self.state.message = "授权未完成或已过期，请重新发起。"
            raise RuntimeError(redact((envelope.get("error") or {}).get("message") or proc.stderr))

        verify = self._run(
            larklib.lark_argv(["auth", "status", "--json", "--verify"], profile=self.state.profile),
            timeout=60,
        )
        verify_env = parse_json_envelope(verify)
        if verify.returncode != 0 or verify_env.get("ok") is not True:
            raise RuntimeError("飞书返回授权成功，但 token 在线校验未通过。")
        self.state.add_log("✓ 用户身份授权完成，token 在线校验通过")
        with self.state.lock:
            self.state.phase = "syncing"
            self.state.message = "授权完成，正在同步飞书内容……"
            self.state.sync_started = True
        thread = threading.Thread(target=self.run_sync, name="mind-feishu-sync", daemon=True)
        thread.start()

    def run_sync(self):
        try:
            data_root = Path(os.environ.get("MIND_FEISHU_HOME", "").strip() or ROOT / "raw/private/feishu")
            data_root.mkdir(parents=True, exist_ok=True)
            self._save_nonsecret_settings(data_root)
            plan = sync_plan(self.python, self.state.include_files, self.state.include_messages)
            for index, (label, argv) in enumerate(plan, 1):
                self.state.add_log(f"▶ {index}/{len(plan)} {label}")
                proc = self._run(argv, timeout=3600)
                for line in (proc.stdout or "").splitlines():
                    self.state.add_log(line)
                for line in (proc.stderr or "").splitlines():
                    self.state.add_log(line)
                if proc.returncode != 0:
                    raise RuntimeError(f"{label}失败（退出码 {proc.returncode}）")
            with self.state.lock:
                self.state.phase = "complete"
                self.state.message = f"同步完成，内容已写入 {data_root}"
            self.state.add_log("✓ 首轮同步全部完成；后续重跑为增量同步")
        except Exception as exc:
            with self.state.lock:
                self.state.phase = "sync_failed"
                self.state.message = f"同步中断：{redact(str(exc))}"
            self.state.add_log(f"✗ {exc}")

    def _save_nonsecret_settings(self, data_root: Path):
        meta = data_root / "_meta"
        meta.mkdir(parents=True, exist_ok=True)
        target = meta / "second-brain-install.json"
        payload = {
            "profile": self.state.profile,
            "include_files": self.state.include_files,
            "include_messages": self.state.include_messages,
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "contains_credentials": False,
        }
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def bootstrap(*, install_lark: bool = True):
    """Idempotent local bootstrap. Existing user data is never replaced."""
    if sys.version_info < (3, 9):
        raise RuntimeError("需要 Python 3.9+。")
    for command in ("git",):
        if not shutil.which(command):
            raise RuntimeError(f"缺少依赖：{command}")

    if not (ROOT / "raw").exists():
        result = vault_init.initialize(vault=ROOT.parent / "mind-vault", repo=ROOT)
        if result.skipped:
            raise RuntimeError("内容库初始化未完全成功；以下目录已被占用：" + ", ".join(result.skipped))

    runtime_python = venv_python(ROOT)
    if not runtime_python.exists():
        subprocess.run([sys.executable, "-m", "venv", str(ROOT / ".venv")], check=True)
    requirements = ROOT / "requirements.txt"
    if requirements.exists():
        subprocess.run([str(runtime_python), "-m", "pip", "install", "-r", str(requirements)], cwd=ROOT, check=True)

    if not shutil.which("lark-cli"):
        if not install_lark:
            raise RuntimeError("未安装 lark-cli。")
        npm = shutil.which("npm")
        if not npm:
            raise RuntimeError("未安装 lark-cli，且找不到 npm；请先安装 Node.js。")
        subprocess.run([npm, "install", "-g", "@larksuite/cli"], check=True)


def wizard_html(token: str) -> str:
    core = "".join(f"<li><code>{html.escape(scope)}</code></li>" for scope in CORE_SCOPES)
    files = "".join(f"<li><code>{html.escape(scope)}</code></li>" for scope in FILE_SCOPES)
    messages = "".join(f"<li><code>{html.escape(scope)}</code></li>" for scope in MESSAGE_SCOPES)
    files_option = (
        f'<label class="option"><input id="files" type="checkbox"> 同步我拥有的云盘文件 '
        f'<span class="warn">（额外权限）</span><ul>{files}</ul></label>'
        if module_available("files") else
        '<p class="option"><span class="warn">云盘文件同步模块未包含在当前发行包中。</span></p>'
    )
    messages_option = (
        f'<label class="option"><input id="messages" type="checkbox"> 同步群聊与单聊 '
        f'<span class="warn">（包含他人消息，通常需要管理员审批）</span><ul>{messages}</ul></label>'
        if module_available("messages") else
        '<p class="option"><span class="warn">聊天同步模块未包含在当前发行包中。</span></p>'
    )
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>安装第二大脑 · 飞书授权</title>
<style>
:root{{--ink:#18202a;--muted:#657180;--paper:#f5f2ea;--card:#fffdf8;--accent:#176f5b;--line:#d9d4c8;--warn:#9b5c12}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
main{{max-width:980px;margin:36px auto;padding:0 20px 60px}}h1{{font:700 36px/1.2 Georgia,"Noto Serif SC",serif;margin:0 0 8px}}h2{{font-size:19px;margin:0 0 12px}}.lede{{color:var(--muted);margin:0 0 26px}}.grid{{display:grid;grid-template-columns:1fr 1fr;gap:18px}}.card{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:20px;box-shadow:0 8px 26px #382f2010}}.wide{{grid-column:1/-1}}label{{display:block;font-weight:650;margin:12px 0 5px}}input[type=text],input[type=password]{{width:100%;padding:10px 12px;border:1px solid var(--line);border-radius:8px;background:white}}button,.button{{display:inline-block;border:0;border-radius:9px;padding:10px 15px;background:var(--accent);color:white;text-decoration:none;font-weight:700;cursor:pointer;margin:8px 8px 0 0}}button.secondary,.button.secondary{{background:#e7e2d6;color:var(--ink)}}code{{font-size:13px}}ul{{padding-left:20px}}.option{{display:block;border-top:1px solid var(--line);padding:12px 0;font-weight:400}}.warn{{color:var(--warn)}}#qr{{width:260px;max-width:80%;display:none;margin:15px 0;border:10px solid white}}#log{{background:#121820;color:#d7e1df;border-radius:10px;padding:14px;height:260px;overflow:auto;white-space:pre-wrap;font:12px/1.5 ui-monospace,SFMono-Regular,monospace}}#status{{font-weight:700}}@media(max-width:720px){{.grid{{grid-template-columns:1fr}}}}
</style></head><body><main>
<h1>安装第二大脑</h1><p class="lede">本地安装 · 飞书最小权限授权 · 授权成功后自动增量同步。凭证只进入本机系统钥匙串。</p>
<div class="grid">
<section class="card"><h2>1. 创建飞书自建应用</h2>
<p>打开开发者后台，创建“企业自建应用”。在“开发配置 → 权限管理”开通下列权限，然后创建并发布版本。</p>
<a class="button" href="{FEISHU_DEVELOPER_CONSOLE}" target="_blank" rel="noreferrer">打开飞书开发者后台</a>
<a class="button secondary" href="{OFFICIAL_PERMISSION_DOC}" target="_blank" rel="noreferrer">查看官方权限说明</a>
<h3>默认：文档与知识库</h3><ul>{core}</ul>
{files_option}
{messages_option}
</section>
<section class="card"><h2>2. 配置本机应用</h2>
<p>从飞书应用“凭证与基础信息”复制 App ID 和 App Secret。Secret 仅通过 stdin 交给 lark-cli，不写入本页面日志或仓库。</p>
<label for="appId">App ID</label><input id="appId" type="text" autocomplete="off">
<label for="appSecret">App Secret</label><input id="appSecret" type="password" autocomplete="new-password">
<label for="profile">本机 Profile 名</label><input id="profile" type="text" value="second-brain">
<button onclick="configure()">保存到系统钥匙串</button>
</section>
<section class="card wide"><h2>3. 用户授权并同步</h2>
<p id="status">等待配置</p>
<button onclick="authorize()">生成授权链接和二维码</button>
<button class="secondary" onclick="completeAuth()">授权完成并开始同步</button><br>
<a id="authUrl" class="button" target="_blank" rel="noreferrer" style="display:none">打开飞书授权页</a>
<br><img id="qr" alt="飞书授权二维码">
<div id="log"></div>
</section></div>
</main><script>
const TOKEN={json.dumps(token)};
async function api(path, body){{
  const r=await fetch(path+'?token='+encodeURIComponent(TOKEN),{{method:body?'POST':'GET',headers:body?{{'Content-Type':'application/json'}}:{{}},body:body?JSON.stringify(body):undefined}});
  const data=await r.json(); if(!r.ok) throw new Error(data.error||'请求失败'); return data;
}}
async function configure(){{try{{await api('/api/configure',{{app_id:appId.value,app_secret:appSecret.value,profile:profile.value}});appSecret.value='';await refresh()}}catch(e){{alert(e.message)}}}}
async function authorize(){{try{{const f=document.getElementById('files'),m=document.getElementById('messages');const d=await api('/api/authorize',{{include_files:f?f.checked:false,include_messages:m?m.checked:false}});render(d)}}catch(e){{alert(e.message)}}}}
async function completeAuth(){{try{{const d=await api('/api/complete',{{}});render(d)}}catch(e){{alert(e.message)}}}}
function render(d){{status.textContent=d.message||d.phase;log.textContent=(d.logs||[]).join('\n');log.scrollTop=log.scrollHeight;if(d.verification_url){{authUrl.href=d.verification_url;authUrl.style.display='inline-block'}}else{{authUrl.style.display='none'}}qr.style.display=d.has_qr?'block':'none';if(d.has_qr)qr.src='/qr.png?token='+encodeURIComponent(TOKEN)+'&v='+Date.now()}}
async function refresh(){{try{{render(await api('/api/state'))}}catch(e){{status.textContent=e.message}}}}
setInterval(refresh,1200);refresh();
</script></body></html>"""


class WizardHandler(BaseHTTPRequestHandler):
    server_version = "SecondBrainInstaller/1.0"

    @property
    def app(self):
        return self.server.app  # type: ignore[attr-defined]

    def log_message(self, fmt, *args):
        return

    def _authorized(self) -> bool:
        query = parse_qs(urlparse(self.path).query)
        return secrets.compare_digest((query.get("token") or [""])[0], self.server.session_token)  # type: ignore[attr-defined]

    def _headers(self, status=200, content_type="application/json; charset=utf-8"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'")
        self.end_headers()

    def _json(self, value, status=200):
        self._headers(status)
        self.wfile.write(json.dumps(value, ensure_ascii=False).encode("utf-8"))

    def _body(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length > 65536:
            raise ValueError("请求体过大。")
        return json.loads(self.rfile.read(length) or b"{}")

    def do_GET(self):
        path = urlparse(self.path).path
        if not self._authorized():
            self._json({"error": "会话无效。"}, HTTPStatus.FORBIDDEN)
            return
        if path in ("/", "/wizard"):
            body = wizard_html(self.server.session_token).encode("utf-8")  # type: ignore[attr-defined]
            self._headers(200, "text/html; charset=utf-8")
            self.wfile.write(body)
        elif path == "/api/state":
            self._json(self.app.state.public())
        elif path == "/qr.png":
            qr = self.app.state.qr_png
            if qr is None:
                self._json({"error": "二维码尚未生成。"}, HTTPStatus.NOT_FOUND)
            else:
                self._headers(200, "image/png")
                self.wfile.write(qr)
        else:
            self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self):
        path = urlparse(self.path).path
        if not self._authorized():
            self._json({"error": "会话无效。"}, HTTPStatus.FORBIDDEN)
            return
        try:
            body = self._body()
            if path == "/api/configure":
                self.app.configure(str(body.get("app_id", "")).strip(), str(body.get("app_secret", "")), str(body.get("profile", "second-brain")).strip())
            elif path == "/api/authorize":
                self.app.start_authorization(bool(body.get("include_files")), bool(body.get("include_messages")))
            elif path == "/api/complete":
                self.app.complete_authorization_and_sync()
            else:
                self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
                return
            self._json(self.app.state.public())
        except Exception as exc:
            self.app.state.add_log(f"✗ {exc}")
            self._json({"error": redact(str(exc)), **self.app.state.public()}, HTTPStatus.BAD_REQUEST)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="一键安装第二大脑，并通过本地页面完成飞书授权与同步。")
    parser.add_argument("--host", default="127.0.0.1", choices=("127.0.0.1",), help="安全起见只允许监听本机")
    parser.add_argument("--port", type=int, default=0, help="本地端口；0 表示自动选择")
    parser.add_argument("--no-open", action="store_true", help="不自动打开浏览器")
    parser.add_argument("--skip-bootstrap", action="store_true", help="跳过 Vault/venv/lark-cli 安装（开发调试）")
    parser.add_argument("--no-install-lark", action="store_true", help="缺少 lark-cli 时不自动通过 npm 安装")
    parser.add_argument("--self-check", action="store_true", help="只检查公开安装包完整性并输出 JSON")
    args = parser.parse_args(argv)

    if args.self_check:
        core = {
            "docs": (SCRIPTS / "feishu-backup-docs.py").is_file(),
            "wiki": (SCRIPTS / "feishu-backup-wiki.py").is_file(),
            "vault_init": (SCRIPTS / "vault_init.py").is_file(),
            "larklib": (SCRIPTS / "larklib.py").is_file(),
        }
        optional = {name: module_available(name) for name in ("files", "messages")}
        payload = {
            "ok": all(core.values()),
            "platform": sys.platform,
            "native_windows": os.name == "nt",
            "python": ".".join(map(str, sys.version_info[:3])),
            "core_modules": core,
            "optional_modules": optional,
        }
        print(json.dumps(payload, ensure_ascii=False))
        return 0 if payload["ok"] else 1

    if not args.skip_bootstrap:
        print("▶ 初始化第二大脑本地环境……", flush=True)
        bootstrap(install_lark=not args.no_install_lark)
        print("✓ 本地环境就绪", flush=True)

    state = WizardState()
    app = Installer(state)
    session_token = secrets.token_urlsafe(24)
    server = ThreadingHTTPServer((args.host, args.port), WizardHandler)
    server.app = app  # type: ignore[attr-defined]
    server.session_token = session_token  # type: ignore[attr-defined]
    host, port = server.server_address
    url = f"http://{host}:{port}/wizard?token={session_token}"
    print(f"飞书权限与授权页面：{url}", flush=True)
    print("页面关闭后可按 Ctrl-C 停止安装器；同步在页面中显示进度。", flush=True)
    if not args.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever(poll_interval=0.3)
    except KeyboardInterrupt:
        print("\n安装器已停止。")
    finally:
        server.server_close()
        app.runtime.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
