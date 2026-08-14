"""WorkBuddy 技能包的「源 → 产物」门禁。

**为什么这个包需要专门一道门禁**(2026-08-14 的真实教训):

v1.8 把公开发行包收敛为 Vault-only,六处对外文案全部改到位,唯独
`site/downloads/*.zip` 里的 SKILL.md 漏了——它还在教用户「用公开仓做飞书授权 + 同步」。
漏掉的原因不是疏忽,是**结构性的**:

1. 这个 zip 当时**没有源文件**,仓里只有二进制。改一次得手工解包重打包,
   内容进不了 code review、`git diff` 看不见。
2. `test_publish_privacy.py` 的 `ALLOWED_OPAQUE` 把它从「不可扫描格式禁入公开版」
   里显式豁免,于是**禁忌词门禁也看不见它写了什么**。

结果就是:全仓唯一「有对外内容、却对所有检查不可见」的载体。修法是把它变回
**纯文本源 + 确定性构建 + 本门禁**——源可扫描、产物可复现、漏改会红。

确定性(同源必同字节)不是洁癖:否则每次构建 zip 二进制都变,git 里全是噪音,
「产物是否跟上源」就又变成没人能验的事。
"""
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "skills" / "workbuddy-second-brain"
BUILDER = REPO / "scripts" / "build-skill-package.py"
DOWNLOADS = REPO / "site" / "downloads"
MEMBERS = ("README.md", "SKILL.md", "skill.yaml")

# 发布工具自身不出库(`publish/` 与 `_publish_gates.sh` 都在 DELETE 清单里),
# 所以「运行期门禁怎么判定」这两条只在私有仓有意义——公开树里 source 不到那个 shell,
# 会以 exit 127 假红(实测:2026-08-14 公开树 pytest 因此拦下过一次发布)。
# 判据取**目录**而非文件:`publish/` 还在却少了 gates 脚本,那是私有仓出了事,必须响亮失败
# (同 tests/test_changelog_sync.py 的取舍)。
IN_PUBLIC_TREE = not (REPO / "publish").is_dir()
skip_in_public_tree = pytest.mark.skipif(
    IN_PUBLIC_TREE, reason="公开树不含发布工具,运行期门禁判定只在私有仓可验"
)


def _version() -> str:
    """技能包版本的**单一来源**:skill.yaml。产物名由它推出,不另处维护。"""
    for line in (SRC / "skill.yaml").read_text(encoding="utf-8").splitlines():
        if line.startswith("version:"):
            return line.split(":", 1)[1].strip()
    raise AssertionError("skill.yaml 缺 version 字段")


def _package() -> Path:
    return DOWNLOADS / f"workbuddy-second-brain-skill-v{_version()}.zip"


def test_source_tree_exists():
    """源必须是纯文本、在仓里、可 diff —— 这是整道门禁的前提。"""
    assert SRC.is_dir(), "缺技能包源目录 skills/workbuddy-second-brain/"
    for name in MEMBERS:
        assert (SRC / name).is_file(), f"技能包源缺 {name}"


def test_builder_is_deterministic_and_matches_committed_package(tmp_path):
    """重新构建必须与仓库里已提交的 zip **逐字节相同**。

    这一条同时锁住两件事:①产物确实跟上了源(漏构建即红)
    ②构建是确定性的(同源同字节),否则 git 里的二进制 diff 毫无意义。
    """
    assert BUILDER.is_file(), "缺构建脚本 scripts/build-skill-package.py"
    committed = _package()
    assert committed.is_file(), f"缺已提交的产物:{committed.relative_to(REPO)}"

    out = tmp_path / "rebuilt"
    proc = subprocess.run(
        [sys.executable, str(BUILDER), "--out-dir", str(out)],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    rebuilt = out / committed.name
    assert rebuilt.is_file(), f"构建脚本没产出 {committed.name}:{proc.stdout}"
    assert rebuilt.read_bytes() == committed.read_bytes(), (
        "重新构建的技能包与已提交的不一致 —— 要么源改了没重新构建,要么构建不确定性。"
        f"跑:python3 {BUILDER.relative_to(REPO)}"
    )


def test_package_contains_exactly_the_source_files():
    with zipfile.ZipFile(_package()) as archive:
        assert set(archive.namelist()) == set(MEMBERS), "包内文件集与源不一致"
        for name in MEMBERS:
            assert archive.read(name).decode("utf-8") == (SRC / name).read_text(encoding="utf-8"), \
                f"包内 {name} 与源不一致"
        assert "expert.yaml" not in archive.namelist(), "expert 形态已于 49f13c2 统一为 skill"


def test_skill_states_the_public_package_boundary():
    """**本轮事故的正身**:说明书必须说清公开包做不到飞书同步。

    v1.0.0 的实测词频是「同步 8 / 授权 11 / 飞书 13」而边界词 0 —— 用户照做
    会撞上安装器的 fail-close 报错,看起来像产品坏了。
    """
    skill = (SRC / "SKILL.md").read_text(encoding="utf-8")
    for required, why in [
        ("Vault-only", "公开包的实际形态"),
        ("完整发行包", "飞书授权/同步的唯一归属"),
        ("不含飞书同步连接器", "公开包能力边界的事实句"),
    ]:
        assert required in skill, f"SKILL.md 缺边界表述「{required}」({why})"


def test_skill_keeps_its_safety_boundary():
    """安全边界是这个包的核心价值,改版不得把它改丢(v1.0.0 起的既有契约)。"""
    skill = (SRC / "SKILL.md").read_text(encoding="utf-8")
    assert skill.startswith("---\n"), "SKILL.md 必须有 frontmatter"
    for token in ("App Secret", "access token", "refresh token", "device code"):
        assert token in skill, f"SKILL.md 丢了安全边界条款:{token}"
    assert "sk-" not in skill, "SKILL.md 不得出现密钥形状"


def test_declared_description_is_consistent_between_carriers():
    """两处 description 必须一致 —— 一处改了另一处没改,商店页与技能行为就会背离。"""
    meta = (SRC / "skill.yaml").read_text(encoding="utf-8")
    skill = (SRC / "SKILL.md").read_text(encoding="utf-8")
    meta_desc = next(ln.split(":", 1)[1].strip() for ln in meta.splitlines()
                     if ln.startswith("description:"))
    front = skill.split("---", 2)[1]
    skill_desc = next(ln.split(":", 1)[1].strip() for ln in front.splitlines()
                      if ln.startswith("description:"))
    assert meta_desc == skill_desc, "skill.yaml 与 SKILL.md 的 description 不一致"
    assert "Vault-only" in meta_desc, "description 应点明公开包形态,商店页第一眼就得说清"


def test_no_stale_package_versions_are_shipped():
    """旧版本必须随替换移除:两个版本并存时,用户下到哪个全看运气。"""
    shipped = sorted(p.name for p in DOWNLOADS.glob("workbuddy-second-brain-skill-v*.zip"))
    assert shipped == [_package().name], f"存在过期的技能包版本:{shipped}"


@skip_in_public_tree
def test_runtime_publish_gate_accepts_the_current_package(tmp_path):
    """发布脚本**运行期**的豁免清单必须认得当前产物。

    这条盯的是真实漂移:不可扫描格式的豁免维护在两处——`test_publish_privacy.py`
    的静态推算与 `_publish_gates.sh` 的运行期扫描。2026-08-14 出 v1.0.1 时只改了
    前者,后者仍写死 v1.0.0,于是 6 个发布测试当场变红。与其比对两份清单的文本
    (形状不同,比不了),不如**直接跑那个 shell 函数**问它认不认。
    """
    gates = REPO / "scripts" / "_publish_gates.sh"
    tree = tmp_path / "tree" / "site" / "downloads"
    tree.mkdir(parents=True)
    (tree / _package().name).write_bytes(b"PK\x03\x04 stub")

    proc = subprocess.run(
        ["bash", "-c", f'. "{gates}"; scan_opaque_tree "{tmp_path / "tree"}"'],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, (
        "运行期门禁不认当前技能包版本(发布会被自己的门禁拦下):\n" + proc.stdout + proc.stderr
    )


@skip_in_public_tree
def test_runtime_gate_rejects_the_retired_expert_package(tmp_path):
    """expert 形态已于 49f13c2 统一为 skill 包、2026-08-14 删除,豁免必须同步收窄。

    留着 `(expert|skill)` 那个分支的代价:将来任何人放一个 expert zip 进
    `site/downloads/`,都会被**静默豁免**发出去——而它没有源、不可扫描、没有门禁。
    """
    gates = REPO / "scripts" / "_publish_gates.sh"
    tree = tmp_path / "tree" / "site" / "downloads"
    tree.mkdir(parents=True)
    (tree / "workbuddy-second-brain-expert-v1.0.0.zip").write_bytes(b"PK\x03\x04 stub")

    proc = subprocess.run(
        ["bash", "-c", f'. "{gates}"; scan_opaque_tree "{tmp_path / "tree"}"'],
        capture_output=True, text=True,
    )
    assert proc.returncode != 0, "退役的 expert 包仍被运行期门禁豁免"


def test_expert_package_is_gone():
    assert not list(DOWNLOADS.glob("*expert*")), "expert 包已退役,不应再随公开版发布"


@pytest.mark.parametrize("carrier", ["docs/guide/workbuddy.md", "site/workbuddy.html"])
def test_carriers_link_the_current_package(carrier):
    text = (REPO / carrier).read_text(encoding="utf-8")
    assert _package().name in text, f"{carrier} 未指向当前技能包 {_package().name}"
    assert "workbuddy-second-brain-skill-v1.0.0.zip" not in text, f"{carrier} 仍留有旧版链接"
