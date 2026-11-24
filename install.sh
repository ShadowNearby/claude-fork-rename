#!/usr/bin/env bash
# Install (or remove) the fork-rename UserPromptSubmit hook.
#
#   ./install.sh              install / update
#   ./install.sh --uninstall  remove the hook entry (keeps your config file)
#
# Also works piped, with no checkout on disk -- it fetches what it needs:
#
#   curl -fsSL https://raw.githubusercontent.com/ShadowNearby/claude-fork-rename/main/install.sh | bash
#
# Touches only your Claude config dir ($CLAUDE_CONFIG_DIR, else ~/.claude):
#   hooks/fork-rename.py   the hook itself
#   settings.json          one UserPromptSubmit entry, merged in (backed up)
#   fork-rename.json       a starter config, written only if absent
set -euo pipefail

CONFIG_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || echo .)"
RAW_BASE="${FORK_RENAME_RAW:-https://raw.githubusercontent.com/ShadowNearby/claude-fork-rename/main}"
SETTINGS="$CONFIG_DIR/settings.json"
# Kept as a literal so settings.json stays portable between machines.
HOOK_CMD='python3 -I "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/hooks/fork-rename.py"'
MODE="${1:-install}"

command -v python3 >/dev/null || { echo "需要 python3 / python3 required" >&2; exit 1; }
[ -d "$CONFIG_DIR" ] || { echo "找不到 $CONFIG_DIR —— 先跑一次 Claude Code / run Claude Code once first" >&2; exit 1; }

if [ "$MODE" = "--uninstall" ]; then
  MODE=uninstall
elif [ "$MODE" != "install" ]; then
  echo "用法 / usage: $0 [--uninstall]" >&2; exit 2
fi

if [ "$MODE" = "install" ] && [ ! -f "$SRC_DIR/fork-rename.py" ]; then
  # Piped, or run from somewhere else: fetch the files this needs.
  command -v curl >/dev/null || { echo "需要 curl / curl required" >&2; exit 1; }
  FETCH_DIR="$(mktemp -d)"
  trap 'rm -rf "$FETCH_DIR"' EXIT
  for f in fork-rename.py fork-rename.example.json; do
    curl -fsSL "$RAW_BASE/$f" -o "$FETCH_DIR/$f" \
      || { echo "下载失败 / download failed: $RAW_BASE/$f" >&2; exit 1; }
  done
  SRC_DIR="$FETCH_DIR"
  echo "下载到临时目录 / fetched into: $FETCH_DIR"
fi

if [ "$MODE" = "install" ]; then
  mkdir -p "$CONFIG_DIR/hooks"
  cp "$SRC_DIR/fork-rename.py" "$CONFIG_DIR/hooks/fork-rename.py"
  chmod +x "$CONFIG_DIR/hooks/fork-rename.py"
  echo "装好脚本 / installed: $CONFIG_DIR/hooks/fork-rename.py"

  if [ ! -f "$CONFIG_DIR/fork-rename.json" ]; then
    cp "$SRC_DIR/fork-rename.example.json" "$CONFIG_DIR/fork-rename.json"
    echo "写了一份起步配置 / starter config: $CONFIG_DIR/fork-rename.json"
  else
    echo "配置已存在，没动 / config kept: $CONFIG_DIR/fork-rename.json"
  fi
fi

MODE="$MODE" SETTINGS="$SETTINGS" HOOK_CMD="$HOOK_CMD" python3 -I - <<'PY'
import json, os, shutil, sys

mode = os.environ["MODE"]
path = os.environ["SETTINGS"]
cmd = os.environ["HOOK_CMD"]
MARK = "fork-rename.py"

settings = {}
if os.path.exists(path):
    with open(path, encoding="utf-8") as fh:
        body = fh.read().strip()
    if body:
        try:
            settings = json.loads(body)
        except ValueError as exc:
            sys.exit("settings.json 解析不了，先修好再装 / cannot parse settings.json: %s" % exc)
    shutil.copy2(path, path + ".fork-rename.bak")

hooks = settings.setdefault("hooks", {})
groups = hooks.setdefault("UserPromptSubmit", [])

present = any(
    MARK in (entry.get("command") or "")
    for group in groups if isinstance(group, dict)
    for entry in (group.get("hooks") or []) if isinstance(entry, dict)
)

if mode == "install":
    if present:
        print("hook 已登记，没重复加 / hook already registered")
        sys.exit(0)
    entry = {"type": "command", "command": cmd, "timeout": 5}
    for group in groups:                      # reuse a matcher-less group
        if isinstance(group, dict) and not group.get("matcher"):
            group.setdefault("hooks", []).append(entry)
            break
    else:
        groups.append({"hooks": [entry]})
    print("登记到 settings.json / registered in settings.json")
else:
    if not present:
        print("settings.json 里没有这个 hook / nothing to remove")
        sys.exit(0)
    for group in groups:
        if not isinstance(group, dict):
            continue
        group["hooks"] = [
            e for e in (group.get("hooks") or [])
            if not (isinstance(e, dict) and MARK in (e.get("command") or ""))
        ]
    hooks["UserPromptSubmit"] = [g for g in groups if g.get("hooks")]
    if not hooks["UserPromptSubmit"]:
        del hooks["UserPromptSubmit"]
    if not hooks:
        del settings["hooks"]
    print("从 settings.json 摘掉了 / removed from settings.json")

tmp = path + ".fork-rename.tmp"
with open(tmp, "w", encoding="utf-8") as fh:
    json.dump(settings, fh, ensure_ascii=False, indent=2)
    fh.write("\n")
os.replace(tmp, path)
if os.path.exists(path + ".fork-rename.bak"):
    print("改前的备份 / backup: %s.fork-rename.bak" % path)
PY

if [ "$MODE" = "install" ]; then
  if [ -f "$SRC_DIR/fork-topics.py" ]; then
    TOPICS_HINT="python3 $SRC_DIR/fork-topics.py"
  else
    TOPICS_HINT="克隆仓库后跑 fork-topics.py / clone the repo and run fork-topics.py"
  fi
  cat <<EOS

下一步 / next:
  1. 改 $CONFIG_DIR/fork-rename.json 里的 domains，换成你自己的模块名
     edit "domains" to the modules you actually work on
  2. 新开的 fork 会话从第一条有内容的 prompt 起自动改名
     new forks rename themselves from their first real prompt
  3. 侧边栏里现有的那些同名 fork：$TOPICS_HINT
     for forks already in your sidebar, see what each one did
EOS
else
  echo "hooks/fork-rename.py 和标记目录留着没删 / script and markers left in place"
fi
