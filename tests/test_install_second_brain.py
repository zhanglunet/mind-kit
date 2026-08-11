import json
import subprocess
from pathlib import Path

import install_second_brain as mod


def test_scope_selection_is_minimal_by_default_and_additive():
    assert mod.selected_scopes(False, False) == mod.CORE_SCOPES
    assert mod.selected_scopes(True, False) == mod.CORE_SCOPES + mod.FILE_SCOPES
    assert mod.selected_scopes(False, True) == mod.CORE_SCOPES + mod.MESSAGE_SCOPES


def test_sync_plan_smokes_before_full_sync():
    plan = mod.sync_plan("python", include_files=True, include_messages=True)
    labels = [label for label, _ in plan]
    assert labels.index("云文档冒烟（3 篇）") < labels.index("同步我拥有的云文档")
    assert labels.index("云盘文件冒烟（3 个）") < labels.index("同步我拥有的云盘文件")
    assert labels.index("聊天记录冒烟（3 个会话）") < labels.index("同步群聊和单聊")
    assert all(isinstance(argv, list) for _, argv in plan), "命令必须用 argv，不能拼 shell"


def test_redact_covers_token_and_device_code():
    raw = 'app_secret: abc access_token="xyz" device_code=qwerty'
    cleaned = mod.redact(raw)
    assert "abc" not in cleaned
    assert "xyz" not in cleaned
    assert "qwerty" not in cleaned
    assert cleaned.count("[REDACTED]") == 3


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


def test_authorization_device_flow_is_memory_only(tmp_path):
    url = "https://example.test/device?opaque=1%2B2"
    code = "one-time-device-code"

    def fake_runner(argv, **kwargs):
        if argv[:3] == ["lark-cli", "auth", "qrcode"]:
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
