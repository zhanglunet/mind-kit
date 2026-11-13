 # -*- coding: utf-8 -*-
"""PRD-410/T5 测试（trend #1970 的 T5 环节）：知识共建会话 验收试运行。
运行：uv run --with pytest python -m pytest tests/test_knowledge_collab_session.py -q
验收（T1 §6 T5 行「全链两遍逐字节一致+失败演练+链复跑+文档无密钥」）：
  接入点全链演练：改动提出 → 会话 propose/accept → outlet 出口（accepted
  进 个人 Wiki）→ JSONL 落账 → 闸门全 pass；两遍全链产物逐字节一致（确定性
  可复现）；失败演练：rejected 拦截留痕/重复接受 SESSION_STATE_CONFLICT/
  日志删除 LEDGER_DRIFT；链复跑 T2/T3/T4 子进程 exit 0；文档无密钥：T1
  设计文档拼接 needle 扫描+占位符纪律（R5）。零网络；全合成占位。
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
MOD_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from knowledge_collab_session import CollabSessionLedger  # noqa: E402
from knowledge_collab_session_gates import (  # noqa: E402
    accept_gate, append_only_gate, gate_summary, mark_baseline, outlet_gate)

NOW = "2026-11-13T12:00:00Z"


def full_chain():
    """接入点全链：提出→会话→出口→落账→闸门。"""
    led = CollabSessionLedger(None)
    led.propose_change("e-001", "intake", "editor-a（占位）", NOW,
                       {"target": "知识[9]（占位）", "change": "入库条目（占位）"})
    led.propose_change("e-002", "revision", "agent-a（占位）", NOW,
                       {"target": "知识[9]修订（占位）", "change": "修订建议（占位）"})
    led.reject_change("e-002", "editor-b（占位）", NOW, "误改（占位）")
    led.accept_change("e-001", "editor-b（占位）", NOW)
    out = led.outlet([{"entry_id": "e-001", "change": "入库条目（占位）"},
                      {"entry_id": "e-002", "change": "修订建议（占位）"}])
    out_entries = [dict(e, reason="会话确认的改动进个人 Wiki（占位）")
                   for e in out["accepted"]]
    with tempfile.TemporaryDirectory() as td:
        disk = CollabSessionLedger(Path(td) / "session" / "log.jsonl")
        disk.propose_change("e-001", "intake", "editor-a（占位）", NOW,
                            {"change": "入库条目（占位）"})
        disk.propose_change("e-002", "revision", "agent-a（占位）", NOW,
                            {"change": "修订建议（占位）"})
        disk.reject_change("e-002", "editor-b（占位）", NOW, "误改（占位）")
        disk.accept_change("e-001", "editor-b（占位）", NOW)
        gates = [append_only_gate(disk), accept_gate(disk), outlet_gate(out)]
        return {"statuses": led.statuses(), "out": out,
                "out_entries": out_entries, "disk_events": disk.events(),
                "summary": gate_summary(gates)}


class TestFullChainDrill(unittest.TestCase):
    def test_chain_twice_byte_identical(self):
        runs = [full_chain(), full_chain()]
        self.assertEqual(json.dumps(runs[0], sort_keys=True),
                         json.dumps(runs[1], sort_keys=True))
        self.assertEqual(runs[0]["summary"]["gate"], "pass")
        self.assertEqual(len(runs[0]["out_entries"]), 1)
        self.assertEqual(runs[0]["out"]["blocked_count"], 1)


class TestFailureDrills(unittest.TestCase):
    def test_rejected_traced_not_in_outlet(self):
        led = CollabSessionLedger(None)
        led.propose_change("e-001", "revision", "agent-a（占位）", NOW)
        led.reject_change("e-001", "editor-b（占位）", NOW, "误改（占位）")
        out = led.outlet([{"entry_id": "e-001"}])
        self.assertEqual(out["accepted"], [])
        self.assertEqual(out["blocked"][0]["status"], "rejected")
        self.assertTrue(any(e["event"] == "reject" for e in led.events()))

    def test_double_accept_conflict_drill(self):
        led = CollabSessionLedger(None)
        led.propose_change("e-001", "revision", "agent-a（占位）", NOW)
        led.accept_change("e-001", "editor-b（占位）", NOW)
        from knowledge_collab_session import SessionError
        with self.assertRaisesRegex(SessionError, "SESSION_STATE_CONFLICT"):
            led.accept_change("e-001", "editor-b（占位）", NOW)

    def test_log_deletion_drift_drill(self):
        led = CollabSessionLedger(None)
        led.propose_change("e-001", "revision", "agent-a（占位）", NOW)
        led.accept_change("e-001", "editor-b（占位）", NOW)
        mark_baseline(led)
        led._events.pop()
        self.assertEqual(append_only_gate(led)["gate"], "LEDGER_DRIFT")


class TestChainRerun(unittest.TestCase):
    def test_t2_t3_t4_rerun_green(self):
        """链复跑：T2/T3/T4 测试子进程复跑 exit 0（链上仍绿实测）。"""
        for name in ("test_knowledge_collab_session.py", "test_knowledge_collab_session_gates.py", "test_prd410_t4_session_boundary.py"):
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", str(SCRIPTS / name)], capture_output=True, timeout=300)
            self.assertEqual(proc.returncode, 0,
                             f"{name} 复跑失败：{proc.stdout[-400:]}")


class TestDocNoSecrets(unittest.TestCase):
    def test_t1_design_doc_no_secrets(self):
        """文档无密钥：T1 设计文档拼接 needle 扫描+占位符纪律（R5）。"""
        repo = Path(__file__).resolve().parents[1]
        doc = next(repo.glob("docs/plans/2026-11-13-prd-410-*.md"))
        text = doc.read_text(encoding="utf-8").lower()
        for needle in ("sk-" + "live", "passw" + "ord", "api_k" + "ey"):
            self.assertNotIn(needle, text, f"设计文档出现密钥词 {needle}")
        self.assertIn("占位", text)


if __name__ == "__main__":
    unittest.main()
