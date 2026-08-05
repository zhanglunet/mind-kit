"""失败通知(通知层):update-all.sh 挂了要有人知道。

背景:`update-all.sh` / `compile.sh` 的非零退出码**此前没有任何消费者** ——
cron 把 stdout/stderr 全量重定向进日志,失败只体现在日志文本里,没人看。
「失败要能被看见」在编排层与编译层都做到了,通知层是空的(2026-08-04 对抗核验记录)。

四条硬契约,每条都对应一种"通知反而帮倒忙"的方式:

1. **失败才发,成功不打扰** —— 天天来一条"一切正常",很快就没人看了,
   真出事那条也跟着被忽略。
2. **发卡失败绝不掩盖原始失败** —— 退出码必须仍是原始的那个。
   这是最容易写错的一处:`cmd || notify` 会把整体退出码变成 notify 的。
3. **未配置就静默跳过** —— 没配飞书的人(比如笔记本、同事的机器)不该每天
   收到一堆"通知发不出去"的报错,那会把真日志淹掉。
4. **通知内容要能定位问题** —— 至少带上失败的命令与退出码,否则收到卡片
   还得自己去翻日志,等于没通知。
"""
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SH = REPO / "scripts" / "notify-on-failure.sh"


def _run(inner_rc, tmp_path, *, extra_env=None, cmd=None):
    """跑 notify-on-failure.sh 包住一个可控退出码的假命令。

    发卡走 MIND_NOTIFY_CMD 打桩(把参数写进文件),不碰真实飞书。
    """
    sink = tmp_path / "sent.txt"
    stub = tmp_path / "notify-stub.sh"
    stub.write_text(f'#!/usr/bin/env bash\ncat >> {sink!s}\nexit ${{NOTIFY_STUB_RC:-0}}\n',
                    encoding="utf-8")
    stub.chmod(0o755)
    inner = tmp_path / "inner.sh"
    inner.write_text(f'#!/usr/bin/env bash\necho "inner ran"\nexit {inner_rc}\n', encoding="utf-8")
    inner.chmod(0o755)
    env = {**os.environ, "MIND_NOTIFY_CMD": str(stub), **(extra_env or {})}
    r = subprocess.run(["bash", str(SH), *(cmd or ["bash", str(inner)])],
                       capture_output=True, text=True, env=env, timeout=60)
    return r, (sink.read_text(encoding="utf-8") if sink.exists() else "")


def test_syntax_ok():
    assert subprocess.run(["bash", "-n", str(SH)]).returncode == 0


def test_success_sends_nothing(tmp_path):
    """成功不打扰 —— 一条都不发。"""
    r, sent = _run(0, tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert sent == "", "成功时不该发通知:" + sent


def test_failure_sends_notification(tmp_path):
    r, sent = _run(7, tmp_path)
    assert sent, "失败必须发通知:" + (r.stdout + r.stderr)[-400:]


def test_original_exit_code_survives(tmp_path):
    """**最要紧的一条**:包一层之后,退出码仍是被包命令的原值。

    `cmd || notify` 那种写法会把整体退出码变成 notify 的 —— 通知发成功了,
    整条 cron 就"成功"了,原始失败反而被通知**掩盖**掉。
    """
    r, _ = _run(7, tmp_path)
    assert r.returncode == 7, f"退出码必须原样透传,实际 {r.returncode}"


def test_notifier_failure_does_not_mask_original(tmp_path):
    """发卡自己失败时,退出码仍须是**原始失败**的那个,而不是发卡的。

    否则出现最坏的情况:任务挂了、通知也挂了,而整体退出码变成通知的错误码 ——
    两个故障互相掩盖,日志上看是另一回事。
    """
    r, _ = _run(7, tmp_path, extra_env={"NOTIFY_STUB_RC": "3"})
    assert r.returncode == 7, f"发卡失败不许改写原始退出码,实际 {r.returncode}"
    assert "通知" in (r.stdout + r.stderr), "发卡失败本身也要吭一声:" + (r.stdout + r.stderr)[-300:]


def test_unconfigured_is_quiet_and_transparent(tmp_path):
    """没配通知渠道:静默跳过,且**不改退出码**。

    笔记本、同事的机器都没配飞书。每天刷一屏"通知发不出去"会把真日志淹掉。
    """
    inner = tmp_path / "inner.sh"
    inner.write_text('#!/usr/bin/env bash\nexit 5\n', encoding="utf-8")
    inner.chmod(0o755)
    env = {k: v for k, v in os.environ.items() if k != "MIND_NOTIFY_CMD"}
    env["MIND_NOTIFY_CMD"] = ""          # 显式置空 = 未配置
    r = subprocess.run(["bash", str(SH), "bash", str(inner)],
                       capture_output=True, text=True, env=env, timeout=60)
    assert r.returncode == 5, f"未配置时也必须原样透传退出码,实际 {r.returncode}"
    both = r.stdout + r.stderr
    assert "Traceback" not in both and "command not found" not in both, \
        "未配置不该报错刷屏:" + both[-300:]


def test_notification_carries_enough_to_locate_the_problem(tmp_path):
    """通知里要有失败的命令与退出码 —— 否则收到卡片还得自己翻日志。"""
    r, sent = _run(7, tmp_path)
    assert "7" in sent, "要带上退出码:" + sent[:400]
    assert "inner" in sent, "要带上失败的命令:" + sent[:400]


def test_inner_output_still_reaches_stdout(tmp_path):
    """包一层不许吃掉被包命令的输出 —— 日志还是要能看。"""
    r, _ = _run(0, tmp_path)
    assert "inner ran" in r.stdout, "被包命令的输出必须照常出现:" + r.stdout[-300:]
