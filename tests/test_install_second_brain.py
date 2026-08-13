import json
import re
import subprocess
from pathlib import Path

import pytest

import install_second_brain as mod


def test_lark_cli_install_is_version_pinned():
    """FR-DIST-06:lark-cli 是第三方供应链,裸包名安装会把上游任意变更直接放进用户机器。"""
    src = Path(mod.__file__).read_text(encoding="utf-8")
    assert re.search(r"@larksuite/cli@\d+\.\d+\.\d+", src), "npm 安装必须锁定 lark-cli 版本"
    assert '"@larksuite/cli"' not in src, "不得保留未锁版本的裸包名安装"


def test_scope_selection_is_minimal_by_default_and_additive():
    assert mod.selected_scopes(False, False) == mod.CORE_SCOPES
    assert mod.selected_scopes(True, False) == mod.CORE_SCOPES + mod.FILE_SCOPES
    assert mod.selected_scopes(False, True) == mod.CORE_SCOPES + mod.MESSAGE_SCOPES


@pytest.mark.skipif(
    not all(mod.module_available(name) for name in ("docs", "wiki")),
    reason="公开包不含私有 docs/wiki 同步连接器；由不可用提示和执行层防线测试覆盖",
)
def test_sync_plan_smokes_before_full_sync():
    plan = mod.sync_plan("python", include_files=True, include_messages=True)
    labels = [label for label, _ in plan]
    assert labels.index("云文档冒烟（3 篇）") < labels.index("同步我拥有的云文档")
    assert labels.index("云盘文件冒烟（3 个）") < labels.index("同步我拥有的云盘文件")
    assert labels.index("聊天记录冒烟（3 个会话）") < labels.index("同步群聊和单聊")
    assert all(isinstance(argv, list) for _, argv in plan), "命令必须用 argv，不能拼 shell"


def test_sync_plan_refuses_missing_core_connectors(monkeypatch, tmp_path):
    monkeypatch.setattr(mod, "SCRIPTS", tmp_path / "scripts")
    with pytest.raises(RuntimeError, match="不含.*同步连接器.*完整发行包"):
        mod.sync_plan("python", include_files=False, include_messages=False)


def test_redact_covers_token_and_device_code():
    raw = 'app_secret: abc access_token="xyz" device_code=qwerty'
    cleaned = mod.redact(raw)
    assert "abc" not in cleaned
    assert "xyz" not in cleaned
    assert "qwerty" not in cleaned
    assert cleaned.count("[REDACTED]") == 3


@pytest.mark.skipif(
    not all(mod.module_available(name) for name in ("docs", "wiki")),
    reason="公开包不含私有 docs/wiki 同步连接器；由配置不可用提示测试覆盖",
)
def test_configure_passes_secret_only_on_stdin(monkeypatch):
    calls = []

    def fake_runner(argv, **kwargs):
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0, stdout=json.dumps({"ok": True}), stderr="")

    state = mod.WizardState()
    installer = mod.Installer(state, runner=fake_runner)
    try:
        installer.configure("cli_test_app", "super-secret-value", "second-brain")
    finally:
        installer.runtime.cleanup()

    argv, kwargs = calls[0]
    assert "super-secret-value" not in argv
    assert kwargs["input"] == "super-secret-value\n"
    assert "super-secret-value" not in "\n".join(state.logs)
    assert state.phase == "configured"


@pytest.mark.skipif(
    not all(mod.module_available(name) for name in ("docs", "wiki")),
    reason="公开包不含私有 docs/wiki 同步连接器；由不可用提示测试覆盖",
)
def test_authorization_device_flow_is_memory_only(tmp_path):
    url = "https://example.test/device?opaque=1%2B2"
    code = "one-time-device-code"

    def fake_runner(argv, **kwargs):
        if Path(argv[0]).name == "lark-cli" and argv[1:3] == ["auth", "qrcode"]:
            output_name = argv[argv.index("--output") + 1]
            Path(kwargs["cwd"], output_name).write_bytes(b"PNG")
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
        payload = {"ok": True, "data": {"verification_url": url, "device_code": code}}
        return subprocess.CompletedProcess(argv, 0, stdout=json.dumps(payload), stderr="")

    state = mod.WizardState(profile="second-brain")
    installer = mod.Installer(state, runner=fake_runner)
    try:
        installer.start_authorization(False, False)
        assert state.verification_url == url, "授权 URL 必须保持 opaque，不改写"
        assert state.device_code == code
        assert state.qr_png == b"PNG"
        assert not list(tmp_path.rglob("*device*")), "device code 不得落盘"
    finally:
        installer.runtime.cleanup()


@pytest.mark.skipif(
    not all(mod.module_available(name) for name in ("docs", "wiki")),
    reason="公开包不含私有 docs/wiki 同步连接器；配置路径由不可用提示测试覆盖",
)
def test_configure_forces_init_only_in_agent_environments(monkeypatch):
    """--force-init 只在 Agent 宿主(OPENCLAW_HOME/HERMES_HOME)下追加:
    普通机器上误加会静默覆盖用户已有的 lark-cli 配置。"""
    calls = []

    def fake_runner(argv, **kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout=json.dumps({"ok": True}), stderr="")

    monkeypatch.delenv("OPENCLAW_HOME", raising=False)
    monkeypatch.delenv("HERMES_HOME", raising=False)
    installer = mod.Installer(mod.WizardState(), runner=fake_runner)
    try:
        installer.configure("cli_test_app", "secret-value", "second-brain")
    finally:
        installer.runtime.cleanup()
    assert "--force-init" not in calls[0]

    calls.clear()
    monkeypatch.setenv("HERMES_HOME", "/tmp/hermes-home")
    installer = mod.Installer(mod.WizardState(), runner=fake_runner)
    try:
        installer.configure("cli_test_app", "secret-value", "second-brain")
    finally:
        installer.runtime.cleanup()
    assert "--force-init" in calls[0]


def test_authorization_explains_when_public_package_lacks_sync_connectors(monkeypatch, tmp_path):
    """公开安装包不得在授权后才因缺少私有同步脚本而静默失败。"""
    monkeypatch.setattr(mod, "SCRIPTS", tmp_path / "scripts")
    installer = mod.Installer(mod.WizardState())
    try:
        with pytest.raises(RuntimeError, match="不含.*同步连接器.*完整发行包"):
            installer.start_authorization(False, False)
    finally:
        installer.runtime.cleanup()


def test_configuration_explains_when_public_package_lacks_sync_connectors(monkeypatch, tmp_path):
    monkeypatch.setattr(mod, "SCRIPTS", tmp_path / "scripts")
    installer = mod.Installer(mod.WizardState())
    try:
        with pytest.raises(RuntimeError, match="不含.*同步连接器.*完整发行包"):
            installer.configure("cli_test_app", "super-secret-value", "second-brain")
    finally:
        installer.runtime.cleanup()


@pytest.mark.skipif(
    mod.sync_status() == "unavailable",
    reason="公开包使用 Vault-only 页面；由公开模式文案测试覆盖",
)
def test_wizard_page_explains_permission_boundary():
    page = mod.wizard_html("test-token")
    for scope in mod.CORE_SCOPES:
        assert scope in page
    for module, scopes, unavailable_text in (
        ("files", mod.FILE_SCOPES, "云盘文件同步模块未包含"),
        ("messages", mod.MESSAGE_SCOPES, "聊天同步模块未包含"),
    ):
        if mod.module_available(module):
            assert all(scope in page for scope in scopes)
        else:
            assert unavailable_text in page
    if mod.module_available("messages"):
        assert "包含他人消息" in page
    assert "系统钥匙串" in page
    assert "127.0.0.1" not in page  # 页面本身不嵌入固定服务地址


def test_public_wizard_explains_sync_is_unavailable(monkeypatch, tmp_path):
    monkeypatch.setattr(mod, "SCRIPTS", tmp_path / "scripts")
    page = mod.wizard_html("test-token")
    assert "完整发行包" in page
    assert "当前公开包不能执行飞书内容同步" in page
    assert "Vault-only" in page
    assert "授权成功后自动增量同步" not in page
    assert "授权完成并开始同步" not in page
    assert "onclick=\"configure()\"" not in page
    assert "onclick=\"authorize()\"" not in page


def test_public_mode_cli_text_and_bootstrap_do_not_require_lark(monkeypatch, tmp_path):
    monkeypatch.setattr(mod, "SCRIPTS", tmp_path / "scripts")
    assert "Vault-only" in mod.cli_description()
    calls = []
    monkeypatch.setattr(mod, "bootstrap", lambda **kwargs: calls.append(kwargs))
    monkeypatch.setattr(mod, "ThreadingHTTPServer", lambda *args: (_ for _ in ()).throw(KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt):
        mod.main(["--no-open"])
    assert calls == [{"install_lark": False}]
