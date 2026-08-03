"""sage-backend.sh 的行为测试(编译后端切换)。

契约:
- `sage-backend.sh <name>` 把 `config.<name>.yaml` 复制成活动的 `config.yaml`;
- 不带参数报当前活动后端;未知参数 → 非零退出;
- **profile 里不得出现字面密钥**——只能写 `${ENV_VAR}`,由 shell 环境提供。

**必须在合成仓里跑**:这个脚本会覆盖仓库根的 config.yaml。对真实仓库跑一次
测试就把用户的活动后端换掉了(而且是静默的)——同 update-all 那条危险测试一个道理。
"""
import re
import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SH = REPO / "scripts" / "sage-backend.sh"

PROFILES = sorted(p.name for p in REPO.glob("config.*.yaml"))


def _synthetic(tmp_path: Path) -> Path:
    root = tmp_path / "mind"
    (root / "scripts").mkdir(parents=True)
    shutil.copy(SH, root / "scripts" / "sage-backend.sh")
    for p in REPO.glob("config.*.yaml"):
        shutil.copy(p, root / p.name)
    shutil.copy(REPO / "config.yaml", root / "config.yaml")
    return root


def _run(root: Path, *args):
    return subprocess.run(["bash", str(root / "scripts" / "sage-backend.sh"), *args],
                          cwd=str(root), capture_output=True, text=True, timeout=30)


def test_syntax_ok():
    assert subprocess.run(["bash", "-n", str(SH)]).returncode == 0


def test_every_profile_is_switchable_and_detected(tmp_path):
    """每个 config.<name>.yaml 都必须能切过去,并且切完能被认出来。

    `current()` 靠 base_url 里的域名判断 —— 加了 profile 却忘了加识别分支的话,
    状态会报 unknown,而切换本身"成功"了。这种半生效最难查。
    """
    root = _synthetic(tmp_path)
    for prof in PROFILES:
        name = prof[len("config."):-len(".yaml")]
        r = _run(root, name)
        assert r.returncode == 0, f"{name} 切换失败:{r.stdout}{r.stderr}"
        assert (root / "config.yaml").read_text(encoding="utf-8") == \
            (root / prof).read_text(encoding="utf-8"), f"{name}:config.yaml 内容没换过去"
        s = _run(root, "status")
        assert name in s.stdout, f"{name} 切过去了却认不出来(current() 少了识别分支):{s.stdout}"


def test_unknown_backend_nonzero(tmp_path):
    root = _synthetic(tmp_path)
    r = _run(root, "nosuchbackend")
    assert r.returncode != 0
    assert "未知" in (r.stdout + r.stderr)


def test_usage_lists_every_available_profile(tmp_path):
    """用法提示要列全所有 profile —— 加了新后端却没在提示里露面等于没加。"""
    root = _synthetic(tmp_path)
    out = _run(root).stdout
    for prof in PROFILES:
        name = prof[len("config."):-len(".yaml")]
        assert name in out, f"用法提示里缺 {name}:{out}"


def test_no_literal_api_key_in_any_profile():
    """profile 里只能写 ${ENV_VAR},不得出现字面密钥。

    断言用**形态**而非字面值:把真 key 写进测试等于换个文件泄露。
    `sk-` 开头 + 一串字符是 OpenAI 兼容网关的通用密钥形态。
    """
    key_shape = re.compile(r"sk-[A-Za-z0-9_\-]{12,}")
    bad = []
    for p in list(REPO.glob("config*.yaml")):
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if key_shape.search(line):
                bad.append(f"{p.name}:{i}")
    assert not bad, "配置文件里出现了字面密钥,改成 ${ENV_VAR}:\n  " + "\n  ".join(bad)


def test_every_profile_reads_key_from_env():
    """每个 profile 的 api_key 都必须是 ${...} 形式。"""
    bad = []
    for p in list(REPO.glob("config*.yaml")):
        for line in p.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if s.startswith("api_key:") and not re.search(r"\$\{[A-Z_]+\}", s):
                bad.append(f"{p.name}: {s[:60]}")
    assert not bad, "api_key 必须走环境变量:\n  " + "\n  ".join(bad)
