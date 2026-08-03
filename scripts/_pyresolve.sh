# scripts/_pyresolve.sh —— 解析「该用哪个 Python」。被其他脚本 source。
#
# 为什么需要:真机上系统 `python3` 可能是 EOL 的 3.6(阿里云 Anolis 3 就是),
# 而项目依赖装在 vm-setup.sh 建的 .venv(3.11)里。裸调 python3 的后果是
# cron 每天全线失败,而且失败信息是一堆莫名其妙的 SyntaxError/AttributeError。
#
# 顺序:
#   1. <repo>/.venv/bin/python           —— 装了依赖的那个,生产环境的正解
#   2. $MIND_PYTHON                       —— 显式指定(测试、特殊部署)
#   3. python3(仅当版本够新)            —— 大多数机器上就是它
#   4. python3.13 / 3.12 / … / 3.9        —— `dnf install python3.11` 之后的真机形状:
#                                            版本化名字有了,但 python3 仍指向 3.6
#   5. 都不行 → stderr 明确告警,仍退回 python3 由调用方决定怎么办
#
# 第 4、5 步是补给"还没建 .venv"的窗口期(新克隆、vm-setup 跑到一半)。
# 没有它们,那段时间里的报错是 `TypeError: __init__() got an unexpected keyword
# argument 'capture_output'` —— 没人能从这句话猜到"你的 python3 太老了"。
MIND_PY_MIN_MINOR=9      # 需要 3.9+

_mind_py_ok() {   # 版本够新?(探测失败/不存在都算不够新)
  "$1" -c "import sys; sys.exit(0 if sys.version_info >= (3, ${MIND_PY_MIN_MINOR}) else 1)" \
    >/dev/null 2>&1
}

mind_python() {
  local repo="${1:-}"
  [ -n "$repo" ] || repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

  if [ -x "$repo/.venv/bin/python" ]; then
    printf '%s\n' "$repo/.venv/bin/python"
    return 0
  fi
  if [ -n "${MIND_PYTHON:-}" ] && [ -x "${MIND_PYTHON}" ]; then
    printf '%s\n' "$MIND_PYTHON"
    return 0
  fi
  if _mind_py_ok python3; then
    printf '%s\n' "python3"
    return 0
  fi
  local cand
  for cand in python3.13 python3.12 python3.11 python3.10 python3.9; do
    if command -v "$cand" >/dev/null 2>&1 && _mind_py_ok "$cand"; then
      printf '%s\n' "$cand"
      return 0
    fi
  done
  echo "⚠ 找不到 3.${MIND_PY_MIN_MINOR}+ 的 Python(python3 太老,也没有 python3.9~3.13)。" >&2
  echo "  装一个:sudo dnf install -y python3.11 / brew install python@3.11;" >&2
  echo "  或先跑 bash scripts/vm-setup.sh 建 .venv。下面的报错多半由此而来。" >&2
  printf '%s\n' "python3"
}
