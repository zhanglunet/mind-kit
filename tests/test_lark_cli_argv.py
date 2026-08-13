import lark_cli_argv


def test_default_argv_uses_environment_profile(monkeypatch):
    monkeypatch.setenv("MIND_LARK_PROFILE", "acct1")
    monkeypatch.setattr(lark_cli_argv.shutil, "which", lambda name: None)
    assert lark_cli_argv.lark_argv(["auth", "status"]) == [
        "lark-cli", "--profile", "acct1", "auth", "status"
    ]


def test_explicit_empty_profile_disables_environment(monkeypatch):
    monkeypatch.setenv("MIND_LARK_PROFILE", "acct1")
    monkeypatch.setattr(lark_cli_argv.shutil, "which", lambda name: None)
    assert lark_cli_argv.lark_argv(["config", "show"], profile="") == [
        "lark-cli", "config", "show"
    ]


def test_whitespace_profile_is_treated_as_unset(monkeypatch):
    """与 larklib 既有语义对齐:空白 profile 等于没配,不得注入 `--profile " "`。"""
    monkeypatch.setenv("MIND_LARK_PROFILE", "  ")
    monkeypatch.setattr(lark_cli_argv.shutil, "which", lambda name: None)
    assert lark_cli_argv.lark_argv(["auth", "status"]) == ["lark-cli", "auth", "status"]
    assert lark_cli_argv.lark_argv(["auth", "status"], profile=" acct ") == [
        "lark-cli", "--profile", "acct", "auth", "status"
    ]


def test_windows_prefers_cmd_executable(monkeypatch):
    monkeypatch.setattr(lark_cli_argv.os, "name", "nt")
    monkeypatch.setattr(
        lark_cli_argv.shutil,
        "which",
        lambda name: {
            "lark-cli": r"C:\\bin\\lark-cli",
            "lark-cli.cmd": r"C:\\bin\\lark-cli.cmd",
            "lark-cli.exe": r"C:\\bin\\lark-cli.exe",
        }.get(name),
    )
    assert lark_cli_argv.lark_argv(["auth", "status"], profile="acct") == [
        r"C:\\bin\\lark-cli.cmd", "--profile", "acct", "auth", "status"
    ]


def test_windows_uses_exe_when_cmd_is_unavailable(monkeypatch):
    monkeypatch.setattr(lark_cli_argv.os, "name", "nt")
    monkeypatch.setattr(
        lark_cli_argv.shutil,
        "which",
        lambda name: {
            "lark-cli": r"C:\\bin\\lark-cli",
            "lark-cli.exe": r"C:\\bin\\lark-cli.exe",
        }.get(name),
    )
    assert lark_cli_argv.lark_argv(["auth", "status"], profile="acct") == [
        r"C:\\bin\\lark-cli.exe", "--profile", "acct", "auth", "status"
    ]
